"""LumiBox 扩展工具 · 系统层逻辑（无 Qt 依赖）。

覆盖：Python .pyc 反编译/反汇编、PyInstaller 归档提取、局域网设备扫描、
磁盘健康状态、PDF / PPT / PPTX 互转。

反编译部分参考了 GitHub 开源项目的思路（pyinstxtractor 的 CArchive/PYZ 格式、
uncompyle6 / decompyle3 / pycdc 的字节码还原），代码为独立实现，
仅用于分析你自己拥有或已获授权的文件。
"""
from __future__ import annotations

import dis
import importlib.util
import io
import ipaddress
import json
import marshal
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import types
import zlib
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime


def _run(cmd, timeout=60, shell=False):
    kwargs = dict(capture_output=True, timeout=timeout, shell=shell)
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(cmd, **kwargs)


def _out_text(proc) -> str:
    enc = "gbk" if os.name == "nt" else "utf-8"
    return (proc.stdout or b"").decode(enc, errors="ignore") or (proc.stderr or b"").decode(enc, errors="ignore")


# ================================================================ .pyc 反编译
# CPython magic number 主版本对应关系（前两字节小端整数）
_MAGIC_VERSION = {
    3394: "3.7", 3413: "3.8", 3425: "3.9", 3439: "3.10", 3495: "3.11",
    3531: "3.12", 3571: "3.13", 3379: "3.6", 3351: "3.5", 3310: "3.4",
    3230: "3.3", 3180: "3.2", 3000: "3.0 / 3.1",
}


def magic_version(magic: bytes) -> str:
    num = magic[0] | (magic[1] << 8)
    if magic == importlib.util.MAGIC_NUMBER:
        return f"{platform.python_version()}（当前解释器）"
    for threshold, ver in sorted(_MAGIC_VERSION.items(), reverse=True):
        if num >= threshold:
            return f"{ver} 左右"
    return "未知（可能是非 CPython 或更旧版本）"


def read_pyc(path: str) -> dict:
    """读取 .pyc 头部并 marshal 出 code 对象。"""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 8:
        raise ValueError("文件太短，不是有效的 .pyc")
    magic = data[:4]
    num = magic[0] | (magic[1] << 8)
    flags = struct.unpack("<I", data[4:8])[0] if num >= 3394 else 0
    header = 16 if num >= 3394 else (12 if num >= 3200 else 8)
    hash_based = bool(flags & 0b1)
    checked = bool(flags & 0b10)
    ts, src_size, src_hash = None, None, None
    if header >= 16:
        if hash_based:
            src_hash = data[8:16].hex().upper()
        else:
            ts, src_size = struct.unpack("<II", data[8:16])
    elif header == 12:
        ts, src_size = struct.unpack("<II", data[4:12])

    code, err = None, None
    for offset in dict.fromkeys([header, 16, 12, 8]):
        try:
            obj = marshal.loads(data[offset:])
            if isinstance(obj, types.CodeType):
                code, err = obj, None
                break
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
    return {
        "path": path, "size": len(data), "magic": magic.hex(" ").upper(),
        "magic_num": num, "version": magic_version(magic), "header": header,
        "flags": flags, "hash_based": hash_based, "checked": checked,
        "timestamp": (datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else None),
        "source_size": src_size, "source_hash": src_hash,
        "code": code, "marshal_error": err,
    }


def pyc_summary(info: dict) -> str:
    lines = [
        f"文件       {os.path.basename(info['path'])}",
        f"大小       {info['size']} 字节",
        f"Magic      {info['magic']}  ({info['magic_num']})",
        f"适用版本   {info['version']}",
        f"头长度     {info['header']} 字节   标志位 {info['flags']}",
        f"校验方式   {'哈希型' if info['hash_based'] else '时间戳型'}"
        f"{' + 已校验' if info['checked'] else ''}",
        f"源时间戳   {info['timestamp'] or '—'}",
        f"源文件大小 {info['source_size'] if info['source_size'] is not None else '—'}",
    ]
    if info["source_hash"]:
        lines.append(f"源哈希     {info['source_hash']}")
    if info["code"] is None:
        lines.append("")
        lines.append("⚠ 字节码无法由当前解释器反序列化：")
        lines.append(f"  {info['marshal_error']}")
        lines.append("  仍可查看文件头；如需还原源码，请在对应 Python 版本中打开，")
        lines.append("  或使用 pycdc / uncompyle6 等独立反编译器。")
    return "\n".join(lines)


def code_tree(code, depth: int = 0) -> dict:
    g = lambda k, d=None: getattr(code, k, d)
    constants = []
    for c in g("co_consts", ()) or ():
        if isinstance(c, types.CodeType):
            continue
        r = repr(c)
        constants.append(r if len(r) <= 90 else r[:87] + "...")
    node = {
        "name": g("co_name", "?"), "qualname": g("co_qualname", g("co_name", "?")),
        "line": g("co_firstlineno", 0), "argcount": g("co_argcount", 0),
        "nlocals": g("co_nlocals", 0), "flags": g("co_flags", 0),
        "file": g("co_filename", "?"),
        "vars": list(g("co_varnames", ()) or ())[:24],
        "names": list(g("co_names", ()) or ())[:24],
        "consts": constants[:24], "depth": depth, "children": [],
    }
    for c in g("co_consts", ()) or ():
        if isinstance(c, types.CodeType):
            node["children"].append(code_tree(c, depth + 1))
    return node


def code_tree_lines(node: dict, out=None) -> list[str]:
    if out is None:
        out = []
    pad = "    " * node["depth"]
    out.append(f"{pad}◆ {node['qualname']}   (行 {node['line']} · 参数 {node['argcount']} · 局部 {node['nlocals']})")
    if node["depth"] == 0:
        out.append(f"{pad}   源文件: {node['file']}")
        out.append(f"{pad}   全局名: {', '.join(node['names']) or '—'}")
    if node["depth"] <= 1 and node["consts"]:
        out.append(f"{pad}   常量: {' | '.join(node['consts'][:8])}")
    for child in node["children"]:
        code_tree_lines(child, out)
    return out


def disassemble(code, max_chars: int = 400000) -> str:
    buf = io.StringIO()
    try:
        dis.dis(code, file=buf)
    except TypeError:
        dis.dis(code, file=buf, depth=None)
    text = buf.getvalue()
    header = (f"; 反汇编由 CPython {platform.python_version()} 的 dis 模块生成\n"
              f"; 指令语义请参考对应 Python 版本的字节码文档\n" + "=" * 72 + "\n")
    return header + text[:max_chars] + ("\n…（输出过长已截断）" if len(text) > max_chars else "")


def detect_decompilers() -> list[dict]:
    tools = []
    for name in ("uncompyle6", "decompyle3", "pycdc", "pycdas"):
        path = shutil.which(name)
        if path:
            tools.append({"name": name, "path": path})
    for mod, name in (("uncompyle6", "uncompyle6 (模块)"), ("decompyle3", "decompyle3 (模块)"),
                      ("xdis", "xdis")):
        try:
            if importlib.util.find_spec(mod):
                tools.append({"name": name, "path": None})
        except (ImportError, ValueError):
            pass
    return tools


def decompile_source(path: str, tool: str) -> str:
    """调用已安装的反编译器还原源码，返回源码文本。"""
    exe = shutil.which(tool)
    if not exe:
        raise RuntimeError(f"未找到 {tool}，请先 pip install {tool}")
    proc = _run([exe, path], timeout=60)
    text = (proc.stdout or b"").decode("utf-8", errors="replace")
    if not text.strip():
        text = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0 and not text.strip():
        raise RuntimeError(f"{tool} 执行失败（退出码 {proc.returncode}）")
    return text


# ================================================================ PyInstaller 归档
PYINST_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
_COOKIE_NEW = struct.Struct("!8sIIII64s")   # 88 bytes, PyInstaller >= 2.1
_COOKIE_OLD = struct.Struct("!8siiii")      # 24 bytes, PyInstaller <= 2.0
_TOC_ENTRY = struct.Struct("!IIIIBc")       # 18 bytes 起，后接 name
TYPE_NAMES = {"m": "Python 模块", "M": "Python 包", "s": "启动脚本", "z": "PYZ 归档",
              "Z": "PYZ 归档", "b": "二进制扩展", "d": "运行时依赖", "x": "数据文件",
              "o": "运行时选项", "n": "其他"}


def parse_pyinstaller_archive(path: str) -> dict:
    """解析 PyInstaller 单文件 exe 的 CArchive（参考 pyinstxtractor 的格式规范）。"""
    with open(path, "rb") as f:
        data = f.read()
    pos = data.rfind(PYINST_MAGIC)
    if pos < 0:
        raise ValueError("未找到 PyInstaller CArchive 特征码，可能不是 PyInstaller 单文件程序")
    cookie_size = 88 if len(data) - pos >= 88 else 24
    if cookie_size == 88:
        magic, pkg_len, toc_off, toc_len, pyver, pylib = _COOKIE_NEW.unpack(data[pos:pos + 88])
        pylib = pylib.rstrip(b"\0").decode("utf-8", "replace")
    else:
        magic, pkg_len, toc_off, toc_len, pyver = _COOKIE_OLD.unpack(data[pos:pos + 24])
        pylib = ""
    overlay = pos + cookie_size - pkg_len
    if overlay < 0 or toc_off + toc_len > pkg_len:
        raise ValueError("归档长度 / TOC 偏移异常，文件可能已损坏或被加壳")
    toc = data[overlay + toc_off: overlay + toc_off + toc_len]
    entries, p, guard = [], 0, 0
    while p + 18 <= len(toc) and guard < 100000:
        guard += 1
        entry_size, epos, csize, usize, cflag, tcode = _TOC_ENTRY.unpack_from(toc, p)
        if entry_size < 18 or p + entry_size > len(toc):
            break
        name = toc[p + 18:p + entry_size].rstrip(b"\0").decode("utf-8", "replace")
        tcode = tcode.decode("ascii", "replace")
        entries.append({
            "name": name or "(未命名)", "type": tcode,
            "type_name": TYPE_NAMES.get(tcode, f"类型 {tcode!r}"),
            "pos": epos, "csize": csize, "usize": usize,
            "compressed": bool(cflag),
        })
        p += entry_size
    return {"data": data, "overlay": overlay, "path": path,
            "python_version": f"{(pyver >> 24) & 0xFF}.{(pyver >> 16) & 0xFF}",
            "pylib": pylib, "pkg_len": pkg_len, "cookie_size": cookie_size,
            "entries": entries}


def _safe_name(name: str) -> str:
    parts = [p for p in re.split(r"[\\/]+", name) if p not in ("", ".", "..")]
    return os.path.join(*parts) if parts else "unnamed.bin"


def archive_entry_bytes(info: dict, entry: dict) -> bytes:
    start = info["overlay"] + entry["pos"]
    raw = info["data"][start:start + entry["csize"]]
    if entry["compressed"]:
        raw = zlib.decompress(raw)
    return raw


def extract_pyz(raw: bytes) -> tuple[bytes, dict, str | None]:
    """解析 PYZ 归档，返回 (pyc magic, toc dict, 错误说明)。"""
    if raw[:4] != b"PYZ\0":
        return b"", {}, "不是标准 PYZ 数据"
    magic = raw[4:8]
    toc_off = struct.unpack("!I", raw[8:12])[0]
    try:
        toc = marshal.loads(raw[toc_off:])
        return magic, toc, None
    except Exception as exc:  # noqa: BLE001
        return magic, {}, f"PYZ TOC 无法反序列化：{exc}（多为跨 Python 版本所致）"


def extract_archive(path: str, outdir: str, progress=None) -> dict:
    """导出归档内全部文件；PYZ 内模块导出为 .pyc 供其他反编译器使用。"""
    info = parse_pyinstaller_archive(path)
    os.makedirs(outdir, exist_ok=True)
    written, notes = [], []
    total = len(info["entries"])
    for i, e in enumerate(info["entries"], 1):
        try:
            raw = archive_entry_bytes(info, e)
            rel = _safe_name(e["name"])
            dst = os.path.join(outdir, rel)
            os.makedirs(os.path.dirname(dst) or outdir, exist_ok=True)
            with open(dst, "wb") as f:
                f.write(raw)
            written.append({"path": dst, "name": e["name"], "size": len(raw)})
            if e["type"] in ("z", "Z"):
                magic, toc, err = extract_pyz(raw)
                if err:
                    notes.append(f"{e['name']}: {err}")
                else:
                    pyz_dir = os.path.join(outdir, "_PYZ_modules")
                    os.makedirs(pyz_dir, exist_ok=True)
                    for modname, meta in list(toc.items())[:10000]:
                        try:
                            _, mpos, mlen = meta
                            blob = zlib.decompress(raw[mpos:mpos + mlen])
                            header = magic + b"\0" * 12  # 时间戳型 pyc 头
                            fn = os.path.join(pyz_dir, _safe_name(modname) + ".pyc")
                            os.makedirs(os.path.dirname(fn) or pyz_dir, exist_ok=True)
                            with open(fn, "wb") as f:
                                f.write(header + blob)
                            written.append({"path": fn, "name": modname + " (PYZ)", "size": len(blob)})
                        except Exception:  # noqa: BLE001
                            continue
                    notes.append(f"{e['name']}: 已导出 {len(toc)} 个模块的 .pyc")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{e['name']}: {exc}")
        if progress:
            progress(i, total)
    notes.insert(0, f"PyInstaller 归档 · Python {info['python_version']} · "
                    f"运行时库 {info['pylib'] or '内嵌'} · 共 {total} 个顶层条目")
    notes.append("提示：.pyc 可用本页「pyc 反编译」反汇编，或用 pycdc / uncompyle6 还原源码。")
    notes.append("本工具仅用于分析自有或已获授权的程序，请遵守软件许可与适用法律。")
    return {"info": info, "files": written, "notes": notes}


# ================================================================ 局域网扫描
# 常见 OUI 前缀（示例表，未知厂商显示 —）
_OUI = {
    "00:1A:2B": "Cisco", "00:0C:29": "VMware", "00:50:56": "VMware",
    "08:00:27": "VirtualBox", "00:15:5D": "Microsoft Hyper-V", "00:1D:D8": "Microsoft",
    "3C:22:FB": "Apple", "A4:83:E7": "Apple", "F0:18:98": "Apple",
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi",
    "00:1B:44": "Samsung", "AC:BC:32": "Samsung", "5C:CF:7F": "Espressif",
    "18:FE:34": "Espressif", "00:11:22": "CIMSYS", "00:E0:4C": "Realtek",
    "60:6D:3C": "Huawei", "A4:5E:60": "Huawei", "F4:83:CD": "TP-Link",
    "50:C7:BF": "TP-Link", "C8:3A:35": "Tenda", "00:1E:65": "Intel",
    "8C:16:45": "Intel", "D8:3A:DD": "Dell", "F0:1F:AF": "Dell",
}


def oui_vendor(mac: str) -> str:
    if not mac:
        return "—"
    key = mac.upper().replace("-", ":")[:8]
    return _OUI.get(key, "—")


def local_networks() -> list[dict]:
    """列出本机可用网段（自动收窄到 /24 以便快速扫描）。"""
    import psutil
    nets, seen = [], set()
    for iface, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family != socket.AF_INET or not a.address or a.address.startswith("127."):
                continue
            mask = a.netmask or "255.255.255.0"
            try:
                net = ipaddress.ip_network(f"{a.address}/{mask}", strict=False)
            except ValueError:
                continue
            if net.num_addresses < 2:
                continue
            narrowed = ipaddress.ip_network(f"{a.address}/{min(24, net.prefixlen)}", strict=False)
            key = str(narrowed)
            if key in seen:
                continue
            seen.add(key)
            nets.append({"interface": iface, "ip": a.address, "netmask": mask,
                         "network": key, "hosts": min(narrowed.num_addresses - 2, 254)})
    return nets


def _ping(ip: str, timeout_ms: int = 400) -> bool:
    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=(timeout_ms / 1000) + 1.2)
        return p.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def arp_table() -> dict:
    out = {}
    try:
        p = _run(["arp", "-a"], timeout=8)
        for line in _out_text(p).splitlines():
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            n = re.search(r"([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})", line)
            if m and n:
                out[m.group(1)] = n.group(1).upper().replace("-", ":")
    except Exception:  # noqa: BLE001
        pass
    if not out and os.name != "nt":
        try:
            p = _run(["ip", "neigh"], timeout=8)
            for line in _out_text(p).splitlines():
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}).*?lladdr\s+([0-9A-Fa-f:]{17})", line)
                if m:
                    out[m.group(1)] = m.group(2).upper()
        except Exception:  # noqa: BLE001
            pass
    return out


def _reverse_dns(ip: str) -> str:
    try:
        socket.setdefaulttimeout(0.8)
        return socket.gethostbyaddr(ip)[0]
    except Exception:  # noqa: BLE001
        return "—"
    finally:
        socket.setdefaulttimeout(None)


def scan_lan(network: str, progress=None, should_stop=None, threads: int = 64) -> list[dict]:
    """ping 扫描 + ARP 表 + 反向 DNS，返回在线设备列表。"""
    net = ipaddress.ip_network(network.strip(), strict=False)
    hosts = list(net.hosts())
    if len(hosts) > 512:
        hosts = hosts[:512]
    ips = [str(h) for h in hosts]
    alive = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(8, min(int(threads), 96))) as pool:
        futures = {pool.submit(_ping, ip): ip for ip in ips}
        for fut, ip in futures.items():
            if should_stop and should_stop():
                break
            try:
                if fut.result(timeout=20):
                    alive.append(ip)
            except Exception:  # noqa: BLE001
                pass
            done += 1
            if progress and (done % 8 == 0 or done == len(ips)):
                progress(done, len(ips))
    arps = arp_table()
    names = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(_reverse_dns, ip): ip for ip in alive}
        wait(futs, timeout=3)
        for fut, ip in futs.items():
            names[ip] = fut.result() if fut.done() else "—"
    rows = []
    for ip in alive:
        mac = arps.get(ip, "—")
        rows.append({"ip": ip, "mac": mac, "vendor": oui_vendor(mac),
                     "hostname": names.get(ip, "—"), "status": "在线"})
    rows.sort(key=lambda r: tuple(int(x) for x in r["ip"].split(".")))
    # 本机也列入（即便 ping 自己不通）
    for n in local_networks():
        if ipaddress.ip_address(n["ip"]) in net and not any(r["ip"] == n["ip"] for r in rows):
            rows.insert(0, {"ip": n["ip"], "mac": "—", "vendor": "本机",
                            "hostname": socket.gethostname(), "status": "本机"})
    return rows


# ================================================================ 磁盘健康
def disk_health() -> dict:
    import psutil
    res = {"platform": platform.system(), "partitions": [], "io": {},
           "physical": [], "notes": []}
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except (OSError, PermissionError):
            continue
        res["partitions"].append({
            "device": p.device, "mount": p.mountpoint, "fstype": p.fstype,
            "total": u.total, "used": u.used, "free": u.free, "percent": u.percent,
        })
    io = psutil.disk_io_counters()
    if io:
        for k in ("read_count", "write_count", "read_bytes", "write_bytes", "read_time", "write_time"):
            res["io"][k] = getattr(io, k, 0)
    if platform.system() == "Windows":
        _windows_physical(res)
    else:
        _linux_physical(res)
    return res


def _windows_physical(res: dict):
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if ps:
        cmd = [ps, "-NoProfile", "-NonInteractive", "-Command",
               "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,Size,"
               "SpindleSpeed | ConvertTo-Json -Compress"]
        try:
            raw = _out_text(_run(cmd, timeout=25)).strip()
            data = json.loads(raw) if raw else []
            for d in (data if isinstance(data, list) else [data]):
                res["physical"].append({
                    "name": d.get("FriendlyName") or "物理磁盘",
                    "media": d.get("MediaType") or ("HDD" if (d.get("SpindleSpeed") or 0) > 0 else "未知"),
                    "health": d.get("HealthStatus") or "未知",
                    "size": d.get("Size") or 0,
                    "temp": "—", "power_on": "—",
                })
        except Exception as exc:  # noqa: BLE001
            res["notes"].append(f"PowerShell 读取物理磁盘失败：{exc}")
        # SMART 可靠性计数器（部分环境需管理员权限）
        try:
            cmd2 = [ps, "-NoProfile", "-NonInteractive", "-Command",
                    "Get-PhysicalDisk | Get-StorageReliabilityCounter | "
                    "Select-Object Temperature,PowerOnHours,Wear,ReadErrorsTotal,WriteErrorsTotal | "
                    "ConvertTo-Json -Compress"]
            raw2 = _out_text(_run(cmd2, timeout=25)).strip()
            extra = json.loads(raw2) if raw2 else []
            extra = extra if isinstance(extra, list) else [extra]
            for i, d in enumerate(extra):
                if i < len(res["physical"]):
                    if d.get("Temperature"):
                        res["physical"][i]["temp"] = f"{d['Temperature']} °C"
                    if d.get("PowerOnHours"):
                        res["physical"][i]["power_on"] = f"{d['PowerOnHours']} 小时"
                    if d.get("Wear") is not None:
                        res["physical"][i]["wear"] = f"{d['Wear']}%"
        except Exception:  # noqa: BLE001
            res["notes"].append("SMART 详细计数器不可用（通常需要管理员权限）")
    else:
        res["notes"].append("未找到 PowerShell，物理磁盘信息不可用")
    if not res["physical"]:
        try:
            raw = _out_text(_run(["wmic", "diskdrive", "get", "Model,Status,Size", "/format:list"], timeout=20))
            for block in raw.split("\n\n"):
                d = dict(re.findall(r"(\w+)\s*=\s*(.+)", block))
                if d.get("Model"):
                    res["physical"].append({"name": d["Model"].strip(), "media": "未知",
                                            "health": d.get("Status", "未知").strip(),
                                            "size": int(d["Size"] or 0) if str(d.get("Size", "")).isdigit() else 0,
                                            "temp": "—", "power_on": "—"})
        except Exception:  # noqa: BLE001
            pass


def _linux_physical(res: dict):
    if shutil.which("lsblk"):
        try:
            raw = _out_text(_run(["lsblk", "-d", "-J", "-b", "-o", "NAME,SIZE,TYPE,ROTA,MODEL"], timeout=15))
            for d in json.loads(raw).get("blockdevices", []):
                if d.get("type") != "disk":
                    continue
                res["physical"].append({
                    "name": d.get("model") or d.get("name", "磁盘"),
                    "media": "HDD" if d.get("rota") else "SSD / 闪存",
                    "health": "需 smartctl", "size": int(d.get("size") or 0),
                    "temp": "—", "power_on": "—",
                })
        except Exception as exc:  # noqa: BLE001
            res["notes"].append(f"lsblk 读取失败：{exc}")
    smart = shutil.which("smartctl")
    if smart and res["physical"]:
        try:
            devs = ["/dev/" + d["name"] for d in res["physical"] if d["name"].startswith(("sd", "nvme", "hd"))]
            for i, dev in enumerate(devs[:len(res["physical"])]):
                raw = _out_text(_run([smart, "-H", "-A", dev], timeout=20))
                m = re.search(r"SMART overall-health self-assessment test result:\s*(\S+)", raw)
                if m:
                    res["physical"][i]["health"] = m.group(1)
                t = re.search(r"(?:194\s+Temperature_Celsius|Temperature:).*?(\d{2,3})", raw)
                if t:
                    res["physical"][i]["temp"] = f"{t.group(1)} °C"
                p = re.search(r"Power_On_Hours.*?\s(\d+)\s", raw)
                if p:
                    res["physical"][i]["power_on"] = f"{p.group(1)} 小时"
        except Exception:  # noqa: BLE001
            pass
    else:
        res["notes"].append("未安装 smartctl，S.M.A.R.T. 健康/温度不可用（Windows 端改用 PowerShell）")


# ================================================================ PDF / PPT / PPTX 互转
def find_libreoffice() -> str | None:
    candidates = [
        shutil.which("soffice"), shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice", "/opt/libreoffice/program/soffice",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def doc_capabilities() -> dict:
    return {
        "LibreOffice": find_libreoffice(),
        "PyMuPDF (fitz)": has_module("fitz") or has_module("pymupdf"),
        "python-pptx": has_module("pptx"),
        "Pillow": has_module("PIL"),
        "reportlab": has_module("reportlab"),
    }


DOC_MATRIX = {
    ".pdf": ["PPTX", "PPT（需 LibreOffice）", "PDF（压缩/拆分另存）"],
    ".pptx": ["PDF", "PPT（需 LibreOffice）"],
    ".ppt": ["PDF（需 LibreOffice）", "PPTX（需 LibreOffice）"],
}


def pdf_to_pptx(src: str, dst: str, dpi: int = 130, progress=None) -> str:
    """把 PDF 每页渲染为图片并嵌入 PPTX（版式完全保真，文本不可编辑）。"""
    import fitz
    from pptx import Presentation
    from pptx.util import Emu
    doc = fitz.open(src)
    if doc.page_count == 0:
        raise ValueError("PDF 不含任何页面")
    prs = Presentation()
    blank = prs.slide_layouts[6]
    first = doc[0].get_pixmap(dpi=dpi)
    prs.slide_width = Emu(int(first.width / dpi * 914400))
    prs.slide_height = Emu(int(first.height / dpi * 914400))
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(dpi=dpi)
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(io.BytesIO(pix.tobytes("png")), 0, 0,
                                 width=prs.slide_width, height=prs.slide_height)
        if progress:
            progress(i, doc.page_count)
    prs.save(dst)
    doc.close()
    return dst


def _find_cjk_font() -> str | None:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def pptx_to_simple_pdf(src: str, dst: str, progress=None) -> str:
    """无 LibreOffice 时的降级方案：提取每页文字渲染为图片再合成 PDF。"""
    from pptx import Presentation
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    prs = Presentation(src)
    W, H = 1280, 720
    font_path = _find_cjk_font()
    font = (ImageFont.truetype(font_path, 26) if font_path else ImageFont.load_default())
    small = (ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default())
    pages = []
    for i, slide in enumerate(prs.slides, 1):
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 8], fill="#5B8DFF")
        d.text((48, 36), f"第 {i} 页  ·  LumiBox 文本版 PDF", fill="#334", font=small)
        y = 92
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for para in shape.text_frame.paragraphs:
                txt = "".join(run.text for run in para.runs) or para.text
                if not txt.strip():
                    continue
                # 简单按字符宽度折行，避免中文溢出
                line = ""
                for ch in txt:
                    if d.textlength(line + ch, font=font) > W - 96:
                        d.text((48, y), line, fill="#172132", font=font)
                        y += 40
                        line = ch
                    else:
                        line += ch
                if line:
                    d.text((48, y), line, fill="#172132", font=font)
                    y += 40
                if y > H - 70:
                    break
            if y > H - 70:
                break
        d.text((48, H - 44), "※ 简版输出：安装 LibreOffice 后可获得完整版式与图片", fill="#889", font=small)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        pages.append(buf)
        if progress:
            progress(i, len(prs.slides))
    c = canvas.Canvas(dst, pagesize=(W * 0.75, H * 0.75))
    for buf in pages:
        c.drawImage(ImageReader(buf), 0, 0, width=W * 0.75, height=H * 0.75)
        c.showPage()
    c.save()
    return dst


def convert_document(src: str, target: str, outdir: str | None = None, progress=None) -> dict:
    """统一转换入口，返回 {path, method, notes}。"""
    if not os.path.isfile(src):
        raise FileNotFoundError("源文件不存在")
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".pdf", ".ppt", ".pptx"):
        raise ValueError("仅支持 .pdf / .ppt / .pptx 文件")
    outdir = outdir or os.path.dirname(os.path.abspath(src))
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    t = target.upper()
    notes = []

    if ext == ".pdf" and t.startswith("PPTX"):
        dst = os.path.join(outdir, base + "_转换.pptx")
        pdf_to_pptx(src, dst, progress=progress)
        return {"path": dst, "method": "PyMuPDF 渲染 + python-pptx",
                "notes": ["每页以高清图片嵌入，版式 100% 保真；文字如需编辑请在 PowerPoint 中另存或 OCR。"]}

    if ext == ".pptx" and t.startswith("PDF") and not find_libreoffice():
        dst = os.path.join(outdir, base + "_转换.pdf")
        pptx_to_simple_pdf(src, dst, progress=progress)
        return {"path": dst, "method": "python-pptx 文本提取（降级方案）",
                "notes": ["未检测到 LibreOffice，已生成「文本版」PDF。",
                          "安装 LibreOffice 后可获得完整版式、图片与图表的 PDF。"]}

    lo = find_libreoffice()
    if not lo:
        raise RuntimeError("该转换需要 LibreOffice（免费开源）。请安装后重试，或选择 PDF → PPTX / PPTX → 简版 PDF。")
    filter_map = {
        ("PDF", ".pptx"): 'pptx:"Impress MS PowerPoint 2007 XML"',
        ("PDF", ".ppt"): 'ppt:"MS PowerPoint 97"',
        ("PPTX", ".ppt"): 'ppt:"MS PowerPoint 97"',
        ("PPTX", ".pdf"): "pdf",
        ("PPT", ".pptx"): 'pptx:"Impress MS PowerPoint 2007 XML"',
        ("PPT", ".pdf"): "pdf",
    }
    target_ext = {"PPTX": ".pptx", "PPT": ".ppt", "PDF": ".pdf"}.get(t.split("（")[0].strip(), ".pdf")
    conv = filter_map.get((t.split("（")[0].strip(), target_ext), target_ext.lstrip("."))
    if ext == ".pdf":
        # LibreOffice 导入 PDF 需要 Draw 的 pdf_import 过滤器
        cmd = [lo, "--headless", "--norestore", "--convert-to", conv,
               '--infilter="impress_pdf_import"', "--outdir", outdir, src]
    else:
        cmd = [lo, "--headless", "--norestore", "--convert-to", conv, "--outdir", outdir, src]
    p = _run(cmd, timeout=180)
    dst = os.path.join(outdir, base + target_ext)
    if not os.path.exists(dst):
        # 部分版本会写成 base.pdf 或不同大小写
        for f in os.listdir(outdir):
            if f.lower().startswith(base.lower()) and f.lower().endswith(target_ext):
                dst = os.path.join(outdir, f)
                break
    if not os.path.exists(dst):
        raise RuntimeError("LibreOffice 未产出目标文件：" + _out_text(p)[:300])
    notes.append("由本机 LibreOffice 离线转换，版式与图片保留较好。")
    return {"path": dst, "method": "LibreOffice headless", "notes": notes}
