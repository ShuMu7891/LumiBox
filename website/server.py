#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LumiBox 官网 · 留言板服务（零依赖，Python 3.8+ 标准库即可运行）

同时做两件事：
  1. 托管静态官网（index.html / style.css / app.js / assets/）
  2. 提供留言 REST API，留言持久化到 data/messages.json —— 所有访客共享，
     不是浏览器本地存储；换设备、换浏览器、清缓存后依然能看到别人的留言。

启动：
    python server.py                 # 默认 0.0.0.0:8080
    LUMIBOX_PORT=9000 python server.py
    LUMIBOX_ADMIN_TOKEN=你的口令 python server.py

环境变量：
    PORT / LUMIBOX_PORT      监听端口，默认 8080
    LUMIBOX_ADMIN_TOKEN      站长口令（删除/导出用），默认 lumibox-admin-2026，上线务必修改
    LUMIBOX_DATA             数据文件，默认 <本文件目录>/data/messages.json
    LUMIBOX_SITE             静态站点目录，默认 <本文件目录>

API 契约：
    GET    /api/health                     健康检查
    GET    /api/stats                      留言总数 / 今日条数
    GET    /api/messages?offset=0&limit=20 分页读取（最新在前，公开）
    POST   /api/messages                   发表留言 {name, content, website?}
    DELETE /api/messages/<id>              删除留言（需 X-Admin-Token）
    GET    /api/export                     导出全部留言（需 X-Admin-Token）

所有响应均为 JSON（除静态文件），统一 {ok: bool, ...}。
"""
from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
SITE = Path(os.environ.get("LUMIBOX_SITE", str(HERE))).resolve()
DATA_FILE = Path(os.environ.get("LUMIBOX_DATA", str(HERE / "data" / "messages.json"))).resolve()
ADMIN_TOKEN = os.environ.get("LUMIBOX_ADMIN_TOKEN", "lumibox-admin-2026")
PORT = int(os.environ.get("LUMIBOX_PORT") or os.environ.get("PORT") or 8080)

NAME_MAX, CONTENT_MAX = 20, 500
PAGE_MAX = 100
BODY_MAX = 16 * 1024
RATE_WINDOW, RATE_MAX = 30, 30          # 同一 IP 30 秒内最多 30 条（宽松，避免反代/NAT 误伤多访客）
DEDUP_WINDOW = 60                       # 60 秒内同 IP 同内容只记一条
KEEP_MAX = 5000                         # 最多保留条数

LOCK = threading.RLock()
RATE: dict[str, list[float]] = {}
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------- 存储层
def _empty_store():
    return {"version": 1, "seq": 0, "messages": []}


def load_store() -> dict:
    """读取留言；文件损坏时备份并重建，不让整站挂掉。"""
    with LOCK:
        if not DATA_FILE.exists():
            return _empty_store()
        try:
            d = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if not isinstance(d, dict) or not isinstance(d.get("messages"), list):
                raise ValueError("bad shape")
            d.setdefault("seq", len(d["messages"]))
            return d
        except Exception as exc:
            bak = DATA_FILE.with_suffix(".corrupt-" + str(int(time.time())) + ".json")
            try:
                DATA_FILE.replace(bak)
                print(f"[warn] 数据文件损坏，已备份到 {bak.name}: {exc}", flush=True)
            except OSError:
                pass
            return _empty_store()


def save_store(store: dict) -> None:
    """原子写入：同目录临时文件 + os.replace，避免并发写半截数据。"""
    with LOCK:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(DATA_FILE.suffix + ".tmp")
        tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, DATA_FILE)


def public_view(m: dict) -> dict:
    """对外只暴露必要字段，不含任何 IP / UA 信息。"""
    return {
        "id": m["id"],
        "seq": m["seq"],
        "name": m["name"],
        "content": m["content"],
        "created_at": m["created_at"],
    }


def add_message(name: str, content: str, ip: str) -> dict:
    with LOCK:
        store = load_store()
        store["seq"] = int(store.get("seq", 0)) + 1
        item = {
            "id": secrets.token_hex(8),
            "seq": store["seq"],
            "name": name,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            # 仅存脱敏摘要用于频率统计，不存明文 IP
            "ip_hash": hashlib.sha256((ip + ADMIN_TOKEN).encode()).hexdigest()[:16],
        }
        store["messages"].append(item)
        if len(store["messages"]) > KEEP_MAX:
            store["messages"] = store["messages"][-KEEP_MAX:]
        save_store(store)
        return public_view(item)


def delete_message(mid: str) -> bool:
    with LOCK:
        store = load_store()
        before = len(store["messages"])
        store["messages"] = [m for m in store["messages"] if m.get("id") != mid]
        if len(store["messages"]) == before:
            return False
        save_store(store)
        return True


def check_rate(ip: str, content: str) -> tuple[bool, str]:
    """限流 + 同内容去重。返回 (是否允许, 拒绝原因)。

    按 IP 的计数故意放宽：站点常部署在反向代理或 NAT 之后，多个真实访客
    会共享同一来源 IP，过严的窗口会把正常访客互相挤掉。刷屏主要靠
    「同一内容短时间重复」与蜜罐字段拦截，管理员也可随时删除。
    """
    now = time.time()
    key = hashlib.sha256((ip + ADMIN_TOKEN).encode()).hexdigest()[:16]
    with LOCK:
        hits = [t for t in RATE.get(key, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_MAX:
            RATE[key] = hits
            return False, "发表太频繁了，请稍后再试"
        # 同内容去重（用存储层最近记录判断，重启后依然有效）
        recent = load_store()["messages"][-40:]
        digest = hashlib.sha256(content.encode()).hexdigest()
        for m in reversed(recent):
            if m.get("ip_hash") == key and \
               hashlib.sha256(m.get("content", "").encode()).hexdigest() == digest:
                try:
                    ts = datetime.fromisoformat(m["created_at"]).timestamp()
                except Exception:
                    continue
                if now - ts < DEDUP_WINDOW:
                    return False, "这条留言刚刚已经发过了"
                break
        hits.append(now)
        RATE[key] = hits
        if len(RATE) > 2000:               # 简单清理，防内存无限增长
            for k in [k for k, v in RATE.items() if not v or now - v[-1] > 600]:
                RATE.pop(k, None)
        return True, ""


def validate(payload: dict):
    """返回 (name, content, error)。字段缺失/空串/类型错误都给明确错误语义。"""
    if not isinstance(payload, dict):
        return None, None, "请求体必须是 JSON 对象"
    # 蜜罐：正常用户看不到也不会填，机器人常会填
    if str(payload.get("website") or "").strip():
        return None, None, "提交被拒绝"
    name = payload.get("name")
    content = payload.get("content")
    if not isinstance(name, str) or not isinstance(content, str):
        return None, None, "昵称和留言内容必须是文本"
    name = CTRL_RE.sub("", name).strip()
    content = CTRL_RE.sub("", content).strip()
    if not name:
        return None, None, "请填写昵称"
    if not content:
        return None, None, "留言内容不能为空"
    if len(name) > NAME_MAX:
        return None, None, f"昵称最多 {NAME_MAX} 个字"
    if len(content) > CONTENT_MAX:
        return None, None, f"留言最多 {CONTENT_MAX} 个字"
    return name, content, None


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "LumiBoxGuestbook/1.0"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        # 精简日志，只保留 API 与异常，静态文件不刷屏
        msg = fmt % args
        if "/api/" in msg or not msg.startswith('"GET /assets'):
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} {msg}", flush=True)

    # ---- 通用响应 ----
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token")
        self.send_header("Access-Control-Max-Age", "86400")

    def json_resp(self, status: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def ok(self, obj=None, status=200):
        d = {"ok": True}
        if obj:
            d.update(obj)
        self.json_resp(status, d)

    def fail(self, msg: str, status=400):
        self.json_resp(status, {"ok": False, "error": msg})

    def client_ip(self) -> str:
        # 仅在有可信反代时采信 X-Forwarded-For；这里只做限流用，影响有限
        xf = self.headers.get("X-Forwarded-For", "")
        return (xf.split(",")[0].strip() if xf else self.client_address[0]) or "unknown"

    def is_admin(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Admin-Token", ""), ADMIN_TOKEN)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    # ---- API ----
    def do_GET(self):
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self.serve_static(u.path)

        if u.path == "/api/health":
            return self.ok({"service": "LumiBox Guestbook", "total": len(load_store()["messages"]),
                            "time": datetime.now(timezone.utc).isoformat(timespec="seconds")})

        if u.path == "/api/stats":
            msgs = load_store()["messages"]
            today = datetime.now(timezone.utc).date().isoformat()
            return self.ok({"total": len(msgs),
                            "today": sum(1 for m in msgs if str(m.get("created_at", "")).startswith(today))})

        if u.path == "/api/messages":
            q = parse_qs(u.query)
            try:
                offset = max(0, int(q.get("offset", ["0"])[0]))
                limit = min(PAGE_MAX, max(1, int(q.get("limit", ["20"])[0])))
            except ValueError:
                return self.fail("offset / limit 必须是整数")
            msgs = load_store()["messages"]
            total = len(msgs)
            # 存储按时间正序追加，返回时倒序（最新在前）
            page = [public_view(m) for m in list(reversed(msgs))[offset:offset + limit]]
            return self.ok({"total": total, "offset": offset, "limit": limit,
                            "has_more": offset + len(page) < total, "items": page})

        if u.path == "/api/export":
            if not self.is_admin():
                return self.fail("管理口令不正确", 403)
            return self.ok({"total": len(load_store()["messages"]),
                            "items": [public_view(m) for m in load_store()["messages"]]})

        return self.fail("接口不存在", 404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/messages":
            return self.fail("接口不存在", 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.fail("请求长度无效")
        if length <= 0:
            return self.fail("请求体为空")
        if length > BODY_MAX:
            return self.fail("请求体过大", 413)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self.fail("JSON 解析失败")

        name, content, err = validate(payload)
        if err:
            return self.fail(err)
        ip = self.client_ip()
        allowed, why = check_rate(ip, content)
        if not allowed:
            return self.fail(why, 429)

        item = add_message(name, content, ip)
        print(f"[guestbook] #{item['seq']} {name}: {content[:40]}", flush=True)
        return self.ok({"item": item, "total": len(load_store()["messages"])}, 201)

    def do_DELETE(self):
        u = urlparse(self.path)
        prefix = "/api/messages/"
        if not u.path.startswith(prefix):
            return self.fail("接口不存在", 404)
        if not self.is_admin():
            return self.fail("管理口令不正确", 403)
        mid = u.path[len(prefix):].strip("/")
        if not mid or not re.fullmatch(r"[0-9a-f]{8,32}", mid):
            return self.fail("留言 ID 无效")
        if not delete_message(mid):
            return self.fail("留言不存在或已删除", 404)
        return self.ok({"deleted": mid, "total": len(load_store()["messages"])})

    # ---- 静态文件 ----
    def serve_static(self, path: str):
        rel = urlparse(path).path.lstrip("/") or "index.html"
        if rel in ("", "/"):
            rel = "index.html"
        target = (SITE / rel).resolve()
        # 目录穿越防护：解析后的路径必须仍在站点目录内
        if SITE not in target.parents and target != SITE:
            return self.fail("禁止访问", 403)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self.fail("文件不存在", 404)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        try:
            body = target.read_bytes()
        except OSError:
            return self.fail("读取失败", 500)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if target.suffix in (".html", ".js", ".css") else "public, max-age=86400")
        self._cors()
        self.end_headers()
        self.wfile.write(body)


def main():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    mimetypes.add_type("image/webp", ".webp")
    mimetypes.add_type("application/javascript", ".js")
    print(f"LumiBox 官网 + 留言板服务", flush=True)
    print(f"  站点目录 : {SITE}", flush=True)
    print(f"  留言数据 : {DATA_FILE}", flush=True)
    print(f"  管理口令 : {'已由环境变量设置' if 'LUMIBOX_ADMIN_TOKEN' in os.environ else '默认值（上线请修改 LUMIBOX_ADMIN_TOKEN）'}", flush=True)
    print(f"  监听地址 : http://0.0.0.0:{PORT}", flush=True)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n已停止", flush=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
