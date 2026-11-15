"""系统增强 / 文件 / 网络类纯逻辑模块（无 UI 依赖，便于自动化测试）。

功能：重复文件查找、批量重命名、文件粉碎、hosts 编辑、启动项/服务、
定时任务命令、端口扫描、网络测速。Windows 特定能力在 Linux 上优雅降级。
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"


# ================================================================ 文件哈希 / 去重
def file_digest(path: str, algo: str = "sha256", chunk: int = 1 << 20) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def quick_digest(path: str, chunk: int = 65536) -> str:
    """首块+尾块+大小，用于快速排除不同文件。"""
    size = os.path.getsize(path)
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        h.update(f.read(chunk))
        if size > chunk * 2:
            f.seek(-chunk, os.SEEK_END)
            h.update(f.read(chunk))
    h.update(struct.pack("<Q", size))
    return h.hexdigest()


def find_duplicates(root: str, min_size: int = 1, recursive: bool = True,
                    progress=None, should_stop=None) -> list[dict]:
    """返回重复文件组：[{hash, size, files:[{path,size,mtime}...]}]。

    先按大小分组，再对同大小文件做快速摘要，最后全量哈希确认，避免误判。
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise ValueError("目录不存在")
    by_size: dict[int, list[str]] = {}
    files: list[str] = []
    walker = os.walk(root) if recursive else [(root, [], os.listdir(root))]
    for dirpath, _dirs, names in walker:
        for name in names:
            p = os.path.join(dirpath, name)
            if not os.path.isfile(p) or os.path.islink(p):
                continue
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if sz < min_size:
                continue
            by_size.setdefault(sz, []).append(p)
            files.append(p)
    candidates = [group for group in by_size.values() if len(group) > 1]
    total = len(candidates)
    done = 0
    result: list[dict] = []
    for group in candidates:
        if should_stop and should_stop():
            break
        stage: dict[str, list[str]] = {}
        for p in group:
            try:
                stage.setdefault(quick_digest(p), []).append(p)
            except OSError:
                continue
        for qgroup in stage.values():
            if len(qgroup) < 2:
                continue
            full: dict[str, list[str]] = {}
            for p in qgroup:
                try:
                    full.setdefault(file_digest(p), []).append(p)
                except OSError:
                    continue
            for digest, dup in full.items():
                if len(dup) > 1:
                    items = [{"path": p,
                              "size": os.path.getsize(p),
                              "mtime": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")}
                             for p in dup]
                    result.append({"hash": digest, "size": os.path.getsize(dup[0]), "files": items})
        done += 1
        if progress:
            progress(done, total)
    result.sort(key=lambda g: g["size"] * (len(g["files"]) - 1), reverse=True)
    return result


def delete_paths(paths: list[str], to_recycle: bool = False) -> dict:
    """删除文件。to_recycle=True 时尽力送入回收站（需 send2trash，否则直接删）。"""
    ok, failed = [], []
    for p in paths:
        try:
            if to_recycle:
                try:
                    import send2trash  # type: ignore
                    send2trash.send2trash(p)
                except Exception:
                    os.remove(p)
            else:
                os.remove(p)
            ok.append(p)
        except Exception as exc:  # noqa: BLE001
            failed.append((p, str(exc)))
    return {"deleted": ok, "failed": failed}


# ================================================================ 批量重命名
def build_rename_plan(files: list[str], mode: str, prefix: str = "", suffix: str = "",
                      find: str = "", replace: str = "", use_regex: bool = False,
                      base: str = "", start: int = 1, pad: int = 0,
                      case: str = "不变", ext_case: str = "不变",
                      keep_ext: bool = True) -> list[dict]:
    """生成重命名预览。返回 [{old, new, dir, changed, conflict}]。

    mode: 序号 | 前缀后缀 | 查找替换 | 大小写 | 时间戳
    不写磁盘，只做纯计算；冲突检测基于目标重名与磁盘已存在文件。
    """
    plan: list[dict] = []
    seen: dict[str, int] = {}
    n = len(files)
    digits = max(pad, len(str(start + n - 1)))
    stamp = datetime.now().strftime("%Y%m%d")
    regex = None
    if mode == "查找替换" and use_regex and find:
        regex = re.compile(find)

    for i, path in enumerate(files):
        p = Path(path)
        directory = str(p.parent)
        stem, ext = p.stem, p.suffix
        new_stem = stem
        new_ext = ext if keep_ext else ""

        if mode == "序号":
            seq = str(start + i).zfill(digits)
            new_stem = f"{base}{seq}"
        elif mode == "前缀后缀":
            new_stem = f"{prefix}{stem}{suffix}"
        elif mode == "查找替换":
            if find:
                sub = (lambda s: regex.sub(replace, s)) if regex else (lambda s: s.replace(find, replace))
                if keep_ext:
                    new_stem = sub(p.stem)
                else:
                    newname = sub(p.name)
                    new_stem, new_ext = Path(newname).stem, Path(newname).suffix
        elif mode == "时间戳":
            new_stem = f"{stem}_{stamp}"
        elif mode == "大小写":
            if case == "全部大写":
                new_stem = stem.upper()
            elif case == "全部小写":
                new_stem = stem.lower()
            elif case == "首字母大写":
                new_stem = " ".join(w[:1].upper() + w[1:] for w in stem.split())
            elif case == "标题化":
                new_stem = stem.title()
            if ext_case == "小写":
                new_ext = new_ext.lower()
            elif ext_case == "大写":
                new_ext = new_ext.upper()

        # 清理非法字符
        new_stem = re.sub(r'[\\/:*?"<>|]', "_", new_stem).strip() or "unnamed"
        new_path = os.path.join(directory, new_stem + new_ext)
        key = new_path.lower() if IS_WINDOWS else new_path
        seen[key] = seen.get(key, 0) + 1
        conflict = seen[key] > 1
        if not conflict and os.path.abspath(new_path) != os.path.abspath(path):
            conflict = os.path.exists(new_path)
        plan.append({"old": path, "new": new_path, "dir": directory,
                     "old_name": p.name, "new_name": os.path.basename(new_path),
                     "changed": os.path.abspath(new_path) != os.path.abspath(path),
                     "conflict": conflict})
    return plan


def apply_rename(plan: list[dict]) -> dict:
    """执行重命名。用两阶段临时名避免交换冲突，返回撤销映射。"""
    active = [e for e in plan if e["changed"] and not e["conflict"]]
    # 冲突预检：目标已存在
    for e in active:
        if os.path.exists(e["new"]) and os.path.abspath(e["new"]) != os.path.abspath(e["old"]):
            return {"ok": [], "failed": [(e["old"], "目标已存在")], "undo": []}
    staged = []
    for i, e in enumerate(active):
        tmp = os.path.join(e["dir"], f".lumibox_tmp_{i}_{os.getpid()}")
        try:
            os.rename(e["old"], tmp)
            staged.append((tmp, e))
        except Exception as exc:  # noqa: BLE001
            for t, _ in staged:
                try:
                    os.rename(t, _["old"])
                except OSError:
                    pass
            return {"ok": [], "failed": [(e["old"], str(exc))], "undo": []}
    ok, failed, undo = [], [], []
    for tmp, e in staged:
        try:
            os.rename(tmp, e["new"])
            ok.append(e["old"])
            undo.append({"from": e["new"], "to": e["old"]})
        except Exception as exc:  # noqa: BLE001
            failed.append((e["old"], str(exc)))
            try:
                os.rename(tmp, e["old"])
            except OSError:
                pass
    return {"ok": ok, "failed": failed, "undo": undo}


def undo_rename(undo: list[dict]) -> dict:
    ok, failed = [], []
    for e in reversed(undo):
        try:
            os.rename(e["from"], e["to"])
            ok.append(e["from"])
        except Exception as exc:  # noqa: BLE001
            failed.append((e["from"], str(exc)))
    return {"ok": ok, "failed": failed}


# ================================================================ 文件粉碎
def shred_file(path: str, passes: int = 3, progress=None) -> dict:
    """多轮覆写后删除（DoD 近似）。对 SSD/日志型文件系统不保证物理不可恢复。"""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return {"path": path, "error": "文件不存在或不是普通文件"}
    size = os.path.getsize(path)
    written = 0
    patterns = (b"\x00", b"\xff", None)  # None = os.urandom
    try:
        with open(path, "r+b", buffering=0) as f:
            for k in range(max(1, passes)):
                f.seek(0)
                remaining = size
                pat = patterns[k % 3]
                while remaining > 0:
                    n = min(1 << 20, remaining)
                    f.write((os.urandom(n) if pat is None else pat * n))
                    remaining -= n
                    if progress:
                        written += n
                        progress(k + 1, max(1, passes), written)
                f.flush()
                os.fsync(f.fileno())
        base = os.path.basename(path)
        tmp = os.path.join(os.path.dirname(path), f".shred_{os.getpid()}_{time.time_ns()}")
        os.rename(path, tmp)
        os.remove(tmp)
        return {"path": path, "name": base, "size": size, "passes": max(1, passes)}
    except Exception as exc:  # noqa: BLE001
        return {"path": path, "error": str(exc)}


# ================================================================ hosts 编辑
def hosts_path() -> str:
    if IS_WINDOWS:
        return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                            "System32", "drivers", "etc", "hosts")
    return "/etc/hosts"


def read_hosts(path: str | None = None) -> str:
    p = path or hosts_path()
    if not os.path.isfile(p):
        return ""
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_hosts(text: str, path: str | None = None) -> dict:
    p = path or hosts_path()
    backup = backup_hosts(p)
    # 归一换行为目标平台风格
    newline = "\r\n" if IS_WINDOWS else "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return {"path": p, "backup": backup, "bytes": len(text.encode("utf-8"))}


def backup_hosts(path: str | None = None) -> str:
    p = path or hosts_path()
    if not os.path.isfile(p):
        return ""
    d = Path.home() / ".lumibox" / "hosts_backup"
    d.mkdir(parents=True, exist_ok=True)
    dst = d / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_hosts.bak")
    shutil.copy2(p, dst)
    return str(dst)


def list_hosts_backups() -> list[dict]:
    d = Path.home() / ".lumibox" / "hosts_backup"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*_hosts.bak"), reverse=True):
        out.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    return out


def parse_hosts(text: str) -> list[dict]:
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        enabled = not line.startswith("#")
        body = line[1:].strip() if line.startswith("#") else line
        body = body.split("#", 1)[0].strip()
        if not body:
            rows.append({"raw": raw, "type": "blank", "ip": "", "host": "", "enabled": True})
            continue
        parts = body.split()
        if len(parts) >= 2 and _valid_ip(parts[0]):
            rows.append({"raw": raw, "type": "entry", "ip": parts[0],
                         "host": parts[1], "comment": " ".join(parts[2:]), "enabled": enabled})
        else:
            rows.append({"raw": raw, "type": "comment", "ip": "", "host": "", "enabled": enabled})
    return rows


def _valid_ip(s: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET, s)
        return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, s)
        return True
    except OSError:
        return False


HOST_PRESETS = {
    "清空自定义解析": "",
    "本地开发常用": "127.0.0.1 localhost\n127.0.0.1 dev.local\n127.0.0.1 api.dev.local\n::1 localhost",
    "屏蔽广告示例": "0.0.0.0 ad.example.com\n0.0.0.0 tracker.example.com",
}


# ================================================================ 启动项 / 服务
def startup_items() -> list[dict]:
    items: list[dict] = []
    if IS_WINDOWS:
        try:
            import winreg  # type: ignore
            roots = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU\\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM\\Run"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU\\RunOnce"),
            ]
            for hive, sub, label in roots:
                try:
                    key = winreg.OpenKey(hive, sub)
                except OSError:
                    continue
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    items.append({"name": name, "command": str(value), "source": label,
                                  "enabled": True, "kind": "registry"})
                    i += 1
                winreg.CloseKey(key)
        except Exception:
            pass
        for env in ("APPDATA", "ProgramData"):
            base = os.environ.get(env)
            if not base:
                continue
            folder = os.path.join(base, r"Microsoft\Windows\Start Menu\Programs\Startup")
            if os.path.isdir(folder):
                for name in os.listdir(folder):
                    items.append({"name": name, "command": os.path.join(folder, name),
                                  "source": "启动文件夹", "enabled": True, "kind": "folder"})
    else:
        d = Path.home() / ".config" / "autostart"
        if d.is_dir():
            for p in sorted(d.glob("*.desktop")):
                name, cmd, enabled = p.stem, "", True
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("Name="):
                        name = line[5:]
                    elif line.startswith("Exec="):
                        cmd = line[5:]
                    elif line.lower().startswith("hidden=true"):
                        enabled = False
                items.append({"name": name, "command": cmd, "source": str(p),
                              "enabled": enabled, "kind": "desktop"})
        sysd = Path("/etc/xdg/autostart")
        if sysd.is_dir():
            for p in sorted(sysd.glob("*.desktop"))[:40]:
                items.append({"name": p.stem, "command": str(p), "source": "系统 autostart",
                              "enabled": True, "kind": "desktop"})
    return items


def toggle_startup(item: dict, enable: bool) -> dict:
    """启用/禁用启动项。Windows 走注册表删除+备份，Linux 改 Hidden 字段。"""
    try:
        if item.get("kind") == "registry" and IS_WINDOWS:
            import winreg  # type: ignore
            mapping = {"HKCU\\Run": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                       "HKLM\\Run": (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                       "HKCU\\RunOnce": (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce")}
            hive, sub = mapping[item["source"]]
            with winreg.OpenKey(hive, sub, 0, winreg.KEY_ALL_ACCESS) as key:
                if enable:
                    winreg.SetValueEx(key, item["name"], 0, winreg.REG_SZ, item["command"])
                else:
                    try:
                        winreg.DeleteValue(key, item["name"])
                    except FileNotFoundError:
                        pass
            return {"ok": True, "name": item["name"], "enabled": enable,
                    "note": "禁用已生效；原值见下方命令，可复制手动恢复"}
        if item.get("kind") == "desktop":
            p = Path(item["source"])
            lines = [l for l in p.read_text(encoding="utf-8", errors="replace").splitlines()
                     if not l.lower().startswith("hidden=")]
            lines.append(f"Hidden={'false' if enable else 'true'}")
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return {"ok": True, "name": item["name"], "enabled": enable}
        return {"ok": False, "error": "此平台不支持修改该启动项，可复制命令手动处理"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}（可能需要管理员权限）"}


def services(limit: int = 300) -> list[dict]:
    out: list[dict] = []
    if IS_WINDOWS:
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "Get-Service | Select-Object -First %d Name,Status,DisplayName | "
                                "ConvertTo-Csv -NoTypeInformation" % limit],
                               capture_output=True, timeout=20)
            import csv, io
            rows = list(csv.DictReader(io.StringIO(r.stdout.decode("utf-8", "replace"))))
            for row in rows:
                out.append({"name": row.get("Name", ""), "status": row.get("Status", ""),
                            "display": row.get("DisplayName", "")})
        except Exception:
            pass
    else:
        try:
            r = subprocess.run(["systemctl", "list-units", "--type=service", "--all",
                                "--no-pager", "--no-legend", "--plain"],
                               capture_output=True, timeout=15)
            for line in r.stdout.decode("utf-8", "replace").splitlines()[:limit]:
                parts = line.split(None, 4)
                if parts and parts[0].endswith(".service"):
                    out.append({"name": parts[0], "status": parts[3] if len(parts) > 3 else "",
                                "display": parts[-1] if len(parts) > 4 else ""})
        except Exception:
            pass
    return out


def service_action(name: str, action: str) -> dict:
    """action: start | stop | restart。需要管理员/SYSTEM 权限。"""
    if action not in ("start", "stop", "restart"):
        raise ValueError("不支持的操作")
    cmd = ["sc", action, name] if IS_WINDOWS else ["systemctl", action, name]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        text = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        return {"ok": r.returncode == 0, "output": text[:600], "command": " ".join(cmd)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": str(exc), "command": " ".join(cmd)}


# ================================================================ 定时任务 / 关机
def shutdown_command(seconds: int, action: str = "关机") -> list[str]:
    if IS_WINDOWS:
        flag = "/s" if action == "关机" else "/r"
        return ["shutdown", flag, "/t", str(int(seconds)), "/c", "LumiBox 定时任务"]
    return ["shutdown", "-h" if action == "关机" else "-r", "+%d" % max(1, int(seconds) // 60)]


def cancel_shutdown_command() -> list[str]:
    return ["shutdown", "/a"] if IS_WINDOWS else ["shutdown", "-c"]


def run_system_command(cmd: list[str]) -> dict:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        return {"ok": r.returncode == 0,
                "output": (r.stdout + r.stderr).decode("utf-8", "replace").strip()[:600],
                "command": " ".join(cmd)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": str(exc), "command": " ".join(cmd)}


def human_countdown(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ================================================================ 端口扫描 / 测速
COMMON_PORTS = {20: "FTP-DATA", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
                53: "DNS", 80: "HTTP", 110: "POP3", 123: "NTP", 135: "RPC",
                139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
                3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 5900: "VNC",
                6379: "Redis", 8080: "HTTP-Alt", 8443: "HTTPS-Alt", 27017: "MongoDB"}


def parse_port_spec(text: str) -> list[int]:
    """支持 '80,443,8000-8100' 与预置名 '常用端口'。"""
    text = (text or "").strip()
    if not text or text in ("常用端口", "common"):
        return sorted(COMMON_PORTS)
    ports: set[int] = set()
    for part in text.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                lo, hi = int(a), int(b)
                ports.update(range(max(1, lo), min(65535, hi) + 1))
            except ValueError:
                continue
        else:
            try:
                ports.add(int(part))
            except ValueError:
                continue
    return sorted(p for p in ports if 1 <= p <= 65535)


def resolve_host(host: str) -> dict:
    host = (host or "127.0.0.1").strip()
    try:
        socket.inet_aton(host)
        return {"host": host, "ip": host, "ok": True}
    except OSError:
        pass
    try:
        ip = socket.gethostbyname(host)
        return {"host": host, "ip": ip, "ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"host": host, "ip": "", "ok": False, "error": str(exc)}


def _probe(ip: str, port: int, timeout: float) -> tuple[int, bool, float]:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return port, True, (time.perf_counter() - t0) * 1000
    except Exception:  # noqa: BLE001
        return port, False, (time.perf_counter() - t0) * 1000


def scan_ports(host: str, ports: list[int], timeout: float = 0.5, threads: int = 120,
               progress=None, should_stop=None) -> list[dict]:
    info = resolve_host(host)
    if not info["ok"]:
        raise ValueError(f"无法解析主机：{info.get('error', host)}")
    ip = info["ip"]
    results: list[dict] = []
    total = len(ports)
    done = 0
    with ThreadPoolExecutor(max_workers=min(threads, max(8, total))) as pool:
        futures = {pool.submit(_probe, ip, p, timeout): p for p in ports}
        for fut in as_completed(futures):
            if should_stop and should_stop():
                break
            port, opened, latency = fut.result()
            if opened:
                results.append({"port": port, "service": COMMON_PORTS.get(port, ""),
                                "state": "开放", "latency": round(latency, 1), "ip": ip})
            done += 1
            if progress:
                progress(done, total)
    results.sort(key=lambda r: r["port"])
    return results


def tcp_latency(host: str, port: int = 80, count: int = 4, timeout: float = 1.5) -> dict:
    info = resolve_host(host)
    if not info["ok"]:
        return {"ok": False, "error": info.get("error", ""), "samples": []}
    samples = []
    for _ in range(count):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((info["ip"], port), timeout=timeout):
                samples.append(round((time.perf_counter() - t0) * 1000, 2))
        except Exception:
            samples.append(None)
    good = [s for s in samples if s is not None]
    return {"ok": bool(good), "host": host, "ip": info["ip"], "port": port,
            "samples": samples, "min": min(good) if good else None,
            "max": max(good) if good else None,
            "avg": round(sum(good) / len(good), 2) if good else None,
            "loss": round((count - len(good)) / count * 100, 1)}


def download_speed(url: str, max_seconds: float = 8.0, max_bytes: int = 24 << 20) -> dict:
    """下载测速：读取指定 URL 计时，返回 Mbps。"""
    import requests
    t0 = time.perf_counter()
    total = 0
    try:
        with requests.get(url, timeout=(4, max_seconds), stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    total += len(chunk)
                if total >= max_bytes or (time.perf_counter() - t0) >= max_seconds:
                    break
        elapsed = max(1e-6, time.perf_counter() - t0)
        return {"ok": True, "bytes": total, "seconds": round(elapsed, 2),
                "mbps": round(total * 8 / elapsed / 1e6, 2),
                "mbs": round(total / elapsed / 1e6, 2), "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "bytes": total, "url": url}


SPEED_URLS = [
    "https://speed.cloudflare.com/__down?bytes=10000000",
    "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png",
    "https://mirrors.aliyun.com/ubuntu/ls-lR.gz",
]
