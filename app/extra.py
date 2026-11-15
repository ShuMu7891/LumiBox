"""LumiBox 扩展工具 · 纯逻辑层（无 Qt 依赖，便于自动化测试）。

覆盖：进制转换 / 编码转换 / 随机数 / UUID 批量 / 二维码编解码 / 转盘决定 / 剪贴板文本清洗。
"""
from __future__ import annotations

import base64
import hashlib
import io
import math
import os
import random
import re
import secrets
import statistics
import struct
import uuid
from datetime import datetime

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


# ================================================================ 进制转换
BASE_LABELS = {2: "BIN 二进制", 8: "OCT 八进制", 10: "DEC 十进制",
               16: "HEX 十六进制", 32: "Base32", 36: "Base36", 64: "Base64 字符"}
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_BITWISE = {
    "AND  &": lambda a, b: a & b,
    "OR  |": lambda a, b: a | b,
    "XOR ^": lambda a, b: a ^ b,
    "<<  左移": lambda a, b: a << b,
    ">>  右移": lambda a, b: a >> b,
}


def parse_number(text: str, base: int = 10) -> int:
    """解析带前缀 / 空格分组的数字，支持任意 2~36 进制。"""
    s = str(text).strip().replace(" ", "").replace("_", "")
    if not s:
        raise ValueError("请输入数值")
    neg = s.startswith("-")
    if neg or s.startswith("+"):
        s = s[1:]
    low = s.lower()
    prefixes = {"0x": 16, "0b": 2, "0o": 8, "0d": 10}
    for pre, pbase in prefixes.items():
        if low.startswith(pre):
            s = s[2:]
            base = pbase if base == 10 else base
            break
    if not 2 <= base <= 36:
        raise ValueError("进制需在 2 ~ 36 之间")
    if not s:
        raise ValueError("缺少有效数字")
    if not all(ch.upper() in DIGITS[:base] for ch in s):
        raise ValueError(f"包含 {base} 进制以外的字符")
    val = 0
    for ch in s.upper():
        val = val * base + DIGITS.index(ch)
    return -val if neg else val


def to_base(value: int, base: int, group: int = 0) -> str:
    """把整数转成指定进制字符串，group>0 时按位分组（如二进制每 4 位空格）。"""
    if not 2 <= base <= 36:
        raise ValueError("进制需在 2 ~ 36 之间")
    if value == 0:
        out = "0"
    else:
        neg = value < 0
        n = abs(int(value))
        chars = []
        while n:
            n, rem = divmod(n, base)
            chars.append(DIGITS[rem])
        out = "".join(reversed(chars))
        if neg:
            out = "-" + out
    if group and base in (2, 8, 16):
        width = {2: 4, 8: 3, 16: 2}[base]
        sign = "-" if out.startswith("-") else ""
        body = out.lstrip("-")
        body = body.rjust(((len(body) + width - 1) // width) * width, "0")
        out = sign + " ".join(body[i:i + width] for i in range(0, len(body), width))
    return out


def base_report(text: str, base: int = 10) -> dict:
    """一次算出常用进制、位宽、字节序与 ASCII 表示。"""
    n = parse_number(text, base)
    bits = n.bit_length()
    width = max(8, 1 << (bits - 1).bit_length()) if bits > 0 else 8
    width = min(max(width, 8), 64)
    unsigned = n & ((1 << width) - 1)
    signed = unsigned - (1 << width) if unsigned >> (width - 1) else unsigned
    raw = unsigned.to_bytes(width // 8, "big", signed=False)
    ascii_repr = "".join(chr(b) if 32 <= b < 127 else "." for b in raw.lstrip(b"\0") or b"\0")
    return {
        "value": n,
        "rows": [
            ("BIN 二进制", to_base(n, 2, group=4)),
            ("OCT 八进制", to_base(n, 8, group=3)),
            ("DEC 十进制", str(n)),
            ("HEX 十六进制", to_base(n, 16, group=4)),
            ("Base32", to_base(n, 32)),
            ("Base36", to_base(n, 36)),
        ],
        "bit_length": bits,
        "width": width,
        "unsigned": unsigned,
        "signed": signed,
        "bytes_hex": raw.hex(" ").upper(),
        "ascii": ascii_repr,
        "float_bits": (struct.unpack(">f", struct.pack(">I", unsigned & 0xFFFFFFFF))[0]
                       if width == 32 else None),
    }


def bitwise(a: int, b: int, op: str, width: int = 64) -> dict:
    fn = _BITWISE.get(op)
    if fn is None:
        raise ValueError("不支持的运算符")
    if op.startswith("<<"):
        b = min(b, 1024)
    result = fn(a, b)
    mask = (1 << width) - 1
    shown = result & mask
    return {"result": result, "shown": shown,
            "dec": str(shown), "hex": to_base(shown, 16, 2),
            "bin": to_base(shown, 2, 4), "width": width}


def char_codes(text: str) -> list[tuple[str, str, str, str]]:
    """字符 -> 码点（十进制 / 十六进制 / UTF-8 字节）。"""
    out = []
    for ch in text[:200]:
        cp = ord(ch)
        out.append((ch if ch.isprintable() and not ch.isspace() else repr(ch),
                    f"U+{cp:04X}", str(cp), ch.encode("utf-8").hex(" ").upper()))
    return out


# ================================================================ 编码转换
ENCODINGS = [
    "UTF-8", "UTF-8-SIG", "UTF-16", "UTF-16-LE", "UTF-16-BE", "UTF-32", "UTF-32-LE",
    "GBK", "GB2312", "GB18030", "BIG5", "BIG5-HKSCS", "SHIFT_JIS", "EUC-JP", "EUC-KR",
    "ASCII", "LATIN-1", "CP1252", "KOI8-R",
]
_MOJIBAKE_PAIRS = [("UTF-8", "GBK"), ("GBK", "UTF-8"), ("UTF-8", "LATIN-1"),
                   ("LATIN-1", "UTF-8"), ("UTF-8", "CP1252"), ("CP1252", "UTF-8"),
                   ("GBK", "BIG5"), ("BIG5", "GBK"), ("UTF-8", "SHIFT_JIS")]


def encode_text(text: str, encoding: str, errors: str = "strict") -> bytes:
    return text.encode(encoding, errors=errors)


def decode_bytes(data: bytes, encoding: str, errors: str = "strict") -> str:
    return data.decode(encoding, errors=errors)


def hex_dump(data: bytes, per_line: int = 16) -> str:
    lines = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        hexs = " ".join(f"{b:02X}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08X}   {hexs:<{per_line * 3}}  {text}")
    return "\n".join(lines) if lines else "(空)"


def encoding_report(text: str, encoding: str) -> dict:
    data = encode_text(text, encoding, errors="replace")
    return {
        "bytes": data,
        "count": len(data),
        "hex": hex_dump(data),
        "base64": base64.b64encode(data).decode("ascii"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bom": data[:4].hex(" ").upper(),
    }


def read_encoded_file(path: str, encoding: str) -> tuple[str, bytes]:
    with open(path, "rb") as f:
        raw = f.read()
    return decode_bytes(raw, encoding, errors="replace"), raw


def write_encoded_file(path: str, text: str, encoding: str) -> int:
    data = encode_text(text, encoding, errors="replace")
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def fix_mojibake(text: str) -> list[tuple[str, str, str]]:
    """尝试常见「A 编码字节被 B 编码解码」组合，返回 [(结果, 源编码, 误读编码)]。"""
    found, seen = [], set()
    for wrong, right in _MOJIBAKE_PAIRS:
        try:
            raw = text.encode(wrong, errors="strict")
            candidate = raw.decode(right, errors="strict")
        except (UnicodeError, LookupError):
            continue
        if candidate == text or candidate in seen:
            continue
        printable = sum(1 for ch in candidate if ch.isprintable() and (ch.isascii() or "\u4e00" <= ch <= "\u9fff"))
        if printable >= len(candidate) * 0.7 and len(candidate) > 0:
            seen.add(candidate)
            found.append((candidate, wrong, right))
    return found[:8]


# ================================================================ 随机数
def random_integers(low: int, high: int, count: int, unique: bool = False,
                    secure: bool = False, sort_result: bool = False) -> list[int]:
    if low > high:
        low, high = high, low
    count = max(1, min(int(count), 100000))
    span = high - low + 1
    if unique and count > span:
        raise ValueError(f"不允许重复时，数量不能超过区间大小 {span}")
    rng = secrets.SystemRandom() if secure else random
    if unique:
        values = rng.sample(range(low, high + 1), count) if not secure else []
        if secure:
            bag = list(range(low, high + 1))
            secrets.SystemRandom().shuffle(bag)
            values = bag[:count]
    else:
        values = [rng.randint(low, high) for _ in range(count)]
    if sort_result:
        values.sort()
    return values


def random_floats(low: float, high: float, count: int, decimals: int = 4,
                  normal: bool = False, secure: bool = False) -> list[float]:
    if low > high:
        low, high = high, low
    count = max(1, min(int(count), 100000))
    decimals = max(0, min(10, int(decimals)))
    out = []
    for _ in range(count):
        if normal:
            mu, sigma = (low + high) / 2, max(1e-9, (high - low) / 6)
            v = (secrets.SystemRandom().gauss(mu, sigma) if secure
                 else random.gauss(mu, sigma))
            v = max(low, min(high, v))
        else:
            v = (secrets.SystemRandom().uniform(low, high) if secure
                 else random.uniform(low, high))
        out.append(round(v, decimals))
    return out


def random_summary(values: list) -> str:
    if not values:
        return "—"
    nums = [float(v) for v in values]
    parts = [f"数量 {len(nums)}", f"最小 {min(nums):g}", f"最大 {max(nums):g}"]
    if len(nums) > 1:
        parts += [f"平均 {statistics.mean(nums):.4g}", f"标准差 {statistics.pstdev(nums):.4g}"]
    return "   ·   ".join(parts)


def pick_from_list(options: list[str], count: int = 1, unique: bool = True) -> list[str]:
    opts = [o.strip() for o in options if o.strip()]
    if not opts:
        raise ValueError("请至少输入一个选项")
    count = max(1, min(int(count), len(opts) if unique else 10000))
    if unique:
        return random.sample(opts, count)
    return [secrets.choice(opts) for _ in range(count)]


# ================================================================ UUID 批量
def uuid_v7() -> uuid.UUID:
    """UUID v7：毫秒时间戳前缀 + 随机位（RFC 9562）。"""
    ms = int(datetime.now().timestamp() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def generate_uuids(version: str, count: int, style: str = "标准", name: str = "") -> list[str]:
    count = max(1, min(int(count), 100000))
    out = []
    for _ in range(count):
        if version == "UUID v1 · 时间+MAC":
            u = uuid.uuid1()
        elif version == "UUID v3 · 名称 MD5":
            u = uuid.uuid3(uuid.NAMESPACE_DNS, name or "lumibox")
        elif version == "UUID v5 · 名称 SHA1":
            u = uuid.uuid5(uuid.NAMESPACE_DNS, name or "lumibox")
        elif version == "UUID v6 · 时间有序":
            # v6 = 重新排布的 v1 时间字段
            u1 = uuid.uuid1()
            t = u1.time
            time_hi = (t >> 32) & 0x0FFF
            time_mid = (t >> 16) & 0xFFFF
            time_lo = t & 0xFFFF
            new_t = (time_lo << 28) | (time_mid << 12) | time_hi
            u = uuid.UUID(int=(new_t << 64) | (0x6 << 60) | (u1.int & ((1 << 60) - 1)))
        elif version == "UUID v7 · 时间有序":
            u = uuid_v7()
        else:
            u = uuid.uuid4()
        s = str(u)
        if style == "大写":
            s = s.upper()
        elif style == "无连字符":
            s = s.replace("-", "")
        elif style == "带花括号":
            s = "{" + s + "}"
        elif style == "URN":
            s = "urn:uuid:" + s
        out.append(s)
    return out


def validate_uuids(lines: list[str]) -> tuple[int, int, list[str]]:
    """返回 (合法数, 非法数, 错误信息列表)。"""
    ok, errs = 0, []
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s:
            continue
        try:
            uuid.UUID(s.strip("{}").replace("urn:uuid:", ""))
            ok += 1
        except ValueError:
            errs.append(f"第 {i} 行不是合法 UUID：{s[:40]}")
    return ok, len(errs), errs


# ================================================================ 二维码
QR_LEVELS = ["L · 低 (7%)", "M · 中 (15%)", "Q · 较高 (25%)", "H · 高 (30%)"]


def make_qr(text: str, level: str = "M · 中 (15%)", box: int = 8,
            fg: str = "#172132", bg: str = "#FFFFFF"):
    import qrcode
    mapping = dict(zip(QR_LEVELS, [qrcode.constants.ERROR_CORRECT_L,
                                  qrcode.constants.ERROR_CORRECT_M,
                                  qrcode.constants.ERROR_CORRECT_Q,
                                  qrcode.constants.ERROR_CORRECT_H]))
    qr = qrcode.QRCode(error_correction=mapping.get(level, qrcode.constants.ERROR_CORRECT_M),
                       box_size=max(2, int(box)), border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fg, back_color=bg)
    pil = img.get_image() if hasattr(img, "get_image") else img
    return pil.convert("RGB")


def decode_qr(source) -> list[dict]:
    """解析图片中的一维/二维码。source 可为路径或 PIL.Image。

    优先 zxing-cpp（跨平台、多码、无需系统库），失败时回退 OpenCV / pyzbar。
    """
    if Image is None:
        raise RuntimeError("缺少 Pillow")
    if isinstance(source, str):
        img = Image.open(source)
    else:
        img = source
    rgb = img.convert("RGB")
    results = []

    try:
        import zxingcpp
        for r in zxingcpp.read_barcodes(rgb):
            results.append({"format": str(getattr(r, "format", "Barcode")),
                             "text": getattr(r, "text", ""),
                             "engine": "zxing-cpp"})
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - 单引擎失败时继续回退
        pass

    if not results:
        try:
            import cv2
            import numpy as np
            arr = np.array(rgb)[:, :, ::-1]
            det = cv2.QRCodeDetector()
            ok, decoded, _, _ = det.detectAndDecodeMulti(arr)
            if ok:
                results.extend({"format": "QR Code", "text": d, "engine": "OpenCV"}
                               for d in decoded if d)
            else:
                single, _, _ = det.detectAndDecode(arr)
                if single:
                    results.append({"format": "QR Code", "text": single, "engine": "OpenCV"})
        except ImportError:
            pass
        except Exception:  # noqa: BLE001
            pass

    if not results:
        try:
            from pyzbar.pyzbar import decode as zdecode
            for r in zdecode(rgb):
                results.append({"format": r.type, "text": r.data.decode("utf-8", "replace"),
                                "engine": "pyzbar"})
        except ImportError:
            pass
        except Exception:  # noqa: BLE001
            pass

    return results


def qr_wifi_payload(ssid: str, password: str, auth: str = "WPA", hidden: bool = False) -> str:
    esc = lambda s: s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace('"', '\\"').replace(":", "\\:")
    return f"WIFI:T:{auth};S:{esc(ssid)};P:{esc(password)};H:{'true' if hidden else 'false'};;"


# ================================================================ 转盘决定
WHEEL_COLORS = ["#5B8DFF", "#8A6BFF", "#FF7AA8", "#FFB547", "#4ECFC0", "#7CC4FF",
                "#C08BFF", "#FF8F6B", "#69D08C", "#F07BC8"]


def wheel_pick(options: list[str]) -> tuple[int, str]:
    if not options:
        raise ValueError("请至少输入一个选项")
    idx = secrets.randbelow(len(options))
    return idx, options[idx]


def wheel_angle_for(index: int, total: int) -> float:
    """返回让指针落在 index 扇区中点所需的转盘旋转角（度）。"""
    if total <= 0:
        return 0.0
    seg = 360.0 / total
    # 指针固定在正上方；扇区 i 的中心角度（自绘时从 -90° 起顺时针）
    center = seg * (index + 0.5)
    return (360.0 - center) % 360.0


# ================================================================ 剪贴板辅助
def clip_preview(text: str, limit: int = 90) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def clip_stats(text: str) -> str:
    s = str(text)
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    words = len(re.findall(r"\b[\w'-]+\b", s))
    return (f"{len(s)} 字符   ·   {len(s.encode('utf-8'))} 字节   ·   "
            f"{words} 单词   ·   {cjk} 汉字   ·   {s.count(chr(10)) + 1} 行")
