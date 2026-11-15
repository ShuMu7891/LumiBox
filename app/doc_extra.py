"""文档 / 格式 / 加密类纯逻辑模块（无 UI 依赖）。

功能：JSON↔YAML↔TOML↔XML 互转、CSV↔Excel 互转、Markdown→HTML/PDF、
密码保险箱（Fernet + PBKDF2）、OCR（pytesseract）、番茄钟与待办数据持久化。
"""
from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / ".lumibox"


# ================================================================ 结构化数据互转
FORMATS = ["JSON", "YAML", "TOML", "XML", "CSV"]


def _json_loads(text: str):
    return json.loads(text)


def parse_yaml(text: str):
    import yaml
    return yaml.safe_load(text)


def parse_toml(text: str):
    import tomllib
    return tomllib.loads(text)


def _xml_to_obj(text: str):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(text)

    def conv(el):
        children = list(el)
        if not children:
            return el.text if el.text is not None else ""
        out: dict = {}
        for c in children:
            v = conv(c)
            if c.tag in out:
                if not isinstance(out[c.tag], list):
                    out[c.tag] = [out[c.tag]]
                out[c.tag].append(v)
            else:
                out[c.tag] = v
        return out
    return {root.tag: conv(root)}


def _csv_to_obj(text: str):
    return list(csv.DictReader(io.StringIO(text)))


def parse_data(text: str, fmt: str):
    fmt = fmt.upper()
    if fmt == "JSON":
        return _json_loads(text)
    if fmt == "YAML":
        return parse_yaml(text)
    if fmt == "TOML":
        return parse_toml(text)
    if fmt == "XML":
        return _xml_to_obj(text)
    if fmt == "CSV":
        return _csv_to_obj(text)
    raise ValueError(f"不支持的源格式：{fmt}")


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def dump_yaml(obj) -> str:
    import yaml
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, default_flow_style=False)


def dump_toml(obj) -> str:
    import tomli_w
    if not isinstance(obj, dict):
        obj = {"data": obj}
    clean = _toml_clean(obj)
    return tomli_w.dumps(clean)


def _toml_clean(obj):
    """TOML 不接受 None / 混合类型数组，做温和归一。"""
    if isinstance(obj, dict):
        return {str(k): _toml_clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_toml_clean(v) if not isinstance(v, (str, int, float, bool)) else v
                for v in obj if v is not None]
    if obj is None:
        return ""
    return obj


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def dump_xml(obj, root: str = "root") -> str:
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    def esc(tag: str) -> str:
        return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]", "_", str(tag)) or "item"

    def build(parent, value, tag="item"):
        if isinstance(value, dict):
            node = ET.SubElement(parent, esc(tag))
            for k, v in value.items():
                build(node, v, k)
        elif isinstance(value, list):
            node = ET.SubElement(parent, esc(tag))
            for v in value:
                build(node, v, "item")
        else:
            node = ET.SubElement(parent, esc(tag))
            node.text = _scalar(value)

    if isinstance(obj, dict) and len(obj) == 1:
        root = next(iter(obj))
        obj = obj[root]
    r = ET.Element(esc(root))
    if isinstance(obj, dict):
        for k, v in obj.items():
            build(r, v, k)
    elif isinstance(obj, list):
        for v in obj:
            build(r, v, "item")
    else:
        r.text = _scalar(obj)
    rough = ET.tostring(r, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def dump_csv(obj) -> str:
    rows = obj if isinstance(obj, list) else (obj.get("rows") if isinstance(obj, dict) else [obj])
    if not rows:
        return ""
    if not isinstance(rows[0], dict):
        rows = [{"value": r} for r in rows]
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: _scalar(v) for k, v in r.items()})
    return out.getvalue()


def convert_data(text: str, src: str, dst: str) -> str:
    obj = parse_data(text, src)
    dst = dst.upper()
    if dst == "JSON":
        return dump_json(obj)
    if dst == "YAML":
        return dump_yaml(obj)
    if dst == "TOML":
        return dump_toml(obj)
    if dst == "XML":
        return dump_xml(obj)
    if dst == "CSV":
        return dump_csv(obj)
    raise ValueError(f"不支持的目标格式：{dst}")


def csv_to_excel(csv_text: str, out_path: str) -> str:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in csv.reader(io.StringIO(csv_text)):
        ws.append(row)
    wb.save(out_path)
    return out_path


def excel_to_csv(path: str, sheet: str | None = None) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
    out = io.StringIO()
    w = csv.writer(out)
    for row in ws.iter_rows(values_only=True):
        w.writerow(["" if v is None else v for v in row])
    wb.close()
    return out.getvalue()


def excel_sheets(path: str) -> list[str]:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names


# ================================================================ Markdown
def md_to_html(text: str, title: str = "LumiBox 文档") -> str:
    import markdown
    body = markdown.markdown(text, extensions=[
        "extra", "tables", "fenced_code", "codehilite", "toc", "sane_lists"])
    css = """
    body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;line-height:1.75;color:#222;
         max-width:860px;margin:36px auto;padding:0 22px;}
    h1,h2,h3{border-bottom:1px solid #e3e8f0;padding-bottom:6px;margin-top:28px;}
    code{background:#f2f5fa;padding:2px 6px;border-radius:5px;font-family:Consolas,monospace;}
    pre{background:#1e2738;color:#e8eefc;padding:16px;border-radius:10px;overflow:auto;}
    pre code{background:none;color:inherit;padding:0;}
    table{border-collapse:collapse;width:100%;}th,td{border:1px solid #d9e0ec;padding:8px 12px;}
    th{background:#f2f6ff;}blockquote{border-left:4px solid #5b8dff;margin:0;padding:4px 16px;color:#556;}
    img{max-width:100%;}a{color:#3b7dff;}
    """
    return (f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            f"<title>{title}</title><style>{css}</style></head><body>{body}</body></html>")


def html_to_pdf(html: str, out_path: str) -> str:
    from weasyprint import HTML
    HTML(string=html).write_pdf(out_path)
    return out_path


def md_stats(text: str) -> dict:
    lines = text.splitlines()
    words = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9']+", text))
    return {"chars": len(text), "words": words, "lines": len(lines),
            "h": len(re.findall(r"^#{1,6}\s", text, re.M)),
            "code": len(re.findall(r"^```", text, re.M)) // 2,
            "links": len(re.findall(r"\[[^\]]*\]\([^)]*\)", text)),
            "images": len(re.findall(r"!\[[^\]]*\]\([^)]*\)", text))}


# ================================================================ 密码保险箱
VAULT_PATH = DATA_DIR / "vault.bin"


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def vault_exists() -> bool:
    return VAULT_PATH.is_file()


def vault_encrypt(entries: list[dict], password: str) -> bytes:
    from cryptography.fernet import Fernet
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    payload = json.dumps(entries, ensure_ascii=False).encode("utf-8")
    token = Fernet(key).encrypt(payload)
    return b"LUMIBOX1" + salt + token


def vault_decrypt(blob: bytes, password: str) -> list[dict]:
    from cryptography.fernet import Fernet, InvalidToken
    if not blob.startswith(b"LUMIBOX1") or len(blob) < 24:
        raise ValueError("保险箱文件格式无效")
    salt, token = blob[8:24], blob[24:]
    key = _derive_key(password, salt)
    try:
        raw = Fernet(key).decrypt(token)
    except InvalidToken as exc:
        raise ValueError("主密码错误或文件已损坏") from exc
    return json.loads(raw.decode("utf-8"))


def vault_save(entries: list[dict], password: str, path: str | None = None) -> str:
    p = Path(path) if path else VAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(vault_encrypt(entries, password))
    return str(p)


def vault_load(password: str, path: str | None = None) -> list[dict]:
    p = Path(path) if path else VAULT_PATH
    if not p.is_file():
        raise ValueError("保险箱尚未创建")
    return vault_decrypt(p.read_bytes(), password)


def vault_export_plain(entries: list[dict]) -> str:
    lines = ["LumiBox 密码保险箱明文导出（请妥善保管，勿外传）",
             f"导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}", "=" * 48]
    for e in entries:
        lines.append(f"[{e.get('category', '未分类')}] {e.get('title', '')}")
        lines.append(f"  账号：{e.get('username', '')}")
        lines.append(f"  密码：{e.get('password', '')}")
        if e.get("url"):
            lines.append(f"  网址：{e['url']}")
        if e.get("note"):
            lines.append(f"  备注：{e['note']}")
        lines.append("")
    return "\n".join(lines)


# ================================================================ OCR
def ocr_capabilities() -> dict:
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return {"ok": False, "langs": [], "error": "未安装 pytesseract / tesseract"}
    try:
        import pytesseract
        langs = pytesseract.get_languages(config="")
        return {"ok": True, "langs": langs,
                "chi": any(x in langs for x in ("chi_sim", "chi_tra"))}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "langs": [], "error": str(exc)}


def ocr_image(source, lang: str = "eng") -> dict:
    """source: 文件路径 / PIL.Image / bytes。"""
    from PIL import Image
    import pytesseract
    if isinstance(source, (str, os.PathLike)):
        img = Image.open(source)
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source))
    else:
        img = source
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    text = pytesseract.image_to_string(img, lang=lang)
    try:
        data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        conf = [int(c) for c, t in zip(data.get("conf", []), data.get("text", []))
                if str(t).strip() and str(c) != "-1"]
        confidence = round(sum(conf) / len(conf), 1) if conf else 0.0
    except Exception:
        confidence = 0.0
    return {"text": text.strip(), "confidence": confidence,
            "size": f"{img.width}×{img.height}", "lang": lang,
            "chars": len(text.strip())}


def ocr_pdf(path: str, lang: str = "eng", max_pages: int = 20, progress=None) -> dict:
    """PDF 文字识别：优先提取文本层，无文本层的页面渲染后 OCR。"""
    import fitz
    from PIL import Image
    import pytesseract
    doc = fitz.open(path)
    n = min(len(doc), max_pages)
    pages = []
    for i in range(n):
        page = doc[i]
        native = page.get_text().strip()
        if len(native) >= 10:
            pages.append({"page": i + 1, "text": native, "source": "文本层"})
        else:
            pix = page.get_pixmap(dpi=170)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            t = pytesseract.image_to_string(img, lang=lang).strip()
            pages.append({"page": i + 1, "text": t, "source": "OCR"})
        if progress:
            progress(i + 1, n)
    doc.close()
    return {"pages": pages, "total_pages": n,
            "text": "\n\n".join(f"—— 第 {p['page']} 页（{p['source']}）——\n{p['text']}" for p in pages),
            "chars": sum(len(p["text"]) for p in pages)}


# ================================================================ 番茄钟 / 待办
TODO_PATH = DATA_DIR / "todos.json"
POMO_PATH = DATA_DIR / "pomodoro.json"


def load_todos() -> list[dict]:
    if not TODO_PATH.is_file():
        return []
    try:
        return json.loads(TODO_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_todos(items: list[dict]) -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TODO_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(TODO_PATH)


def add_todo(text: str, priority: str = "普通") -> dict:
    return {"id": f"{time_ns()}", "text": text.strip(), "priority": priority,
            "done": False, "created": datetime.now().strftime("%Y-%m-%d %H:%M")}


def time_ns() -> int:
    import time
    return time.time_ns()


def pomo_stats() -> dict:
    if not POMO_PATH.is_file():
        return {"sessions": 0, "minutes": 0, "today": 0, "history": []}
    try:
        data = json.loads(POMO_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"sessions": 0, "minutes": 0, "today": 0, "history": []}
    today = datetime.now().strftime("%Y-%m-%d")
    hist = data.get("history", [])
    return {"sessions": len(hist), "minutes": sum(h.get("minutes", 0) for h in hist),
            "today": sum(1 for h in hist if h.get("date") == today), "history": hist}


def pomo_record(minutes: int, mode: str = "专注") -> dict:
    data = {"history": []}
    if POMO_PATH.is_file():
        try:
            data = json.loads(POMO_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    entry = {"date": datetime.now().strftime("%Y-%m-%d"),
             "time": datetime.now().strftime("%H:%M"), "minutes": int(minutes), "mode": mode}
    data.setdefault("history", []).append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POMO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return pomo_stats()
