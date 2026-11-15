"""通用工具函数：剪贴板、线程、图像转换、安全计算、哈希等。"""
from __future__ import annotations

import ast
import hashlib
import math
import operator
from datetime import datetime

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QIcon
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------- 剪贴板 / 提示
def set_clipboard(text: str) -> None:
    QApplication.clipboard().setText(text)


def human_bytes(num: float) -> str:
    if num is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} EB"


def format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    if d:
        return f"{d} 天 {h} 小时 {m} 分"
    if h:
        return f"{h} 小时 {m} 分"
    return f"{m} 分 {s} 秒"


# ---------------------------------------------------------------- 后台线程
class Worker(QThread):
    """在后台执行 fn(*args)，通过信号把结果送回 UI 线程。

    注意：调用方需要持有该 Worker 的引用，避免被 GC 回收。
    """
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args

    def run(self):
        try:
            self.done.emit(self._fn(*self._args))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# ---------------------------------------------------------------- PIL <-> Qt
def pil_to_pixmap(img) -> QPixmap:
    from PIL import Image
    if not isinstance(img, Image.Image):
        raise TypeError("需要 PIL.Image 对象")
    img = img.convert("RGBA")
    raw = img.tobytes("raw", "RGBA")
    qimg = QImage(raw, img.width, img.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def pixmap_to_pil(pix: QPixmap):
    from PIL import Image
    qimg = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(qimg.constBits())
    return Image.frombytes("RGBA", (qimg.width(), qimg.height()), data,
                           "raw", "RGBA", qimg.bytesPerLine())


def make_app_icon(size: int = 128) -> QIcon:
    """运行时用 QPainter 生成应用图标，避免外部资源依赖。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 128.0
    path = QPainterPath()
    path.addRoundedRect(6 * s, 6 * s, 116 * s, 116 * s, 30 * s, 30 * s)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor("#5aa0ff"))
    grad.setColorAt(0.55, QColor("#6f7bff"))
    grad.setColorAt(1, QColor("#b06cff"))
    p.fillPath(path, grad)
    # 顶部高光
    p.save()
    p.setClipPath(path)
    sheen = QLinearGradient(0, 0, 0, size * 0.55)
    sheen.setColorAt(0, QColor(255, 255, 255, 105))
    sheen.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(0, 0, size, size, sheen)
    p.restore()
    p.setPen(QColor(255, 255, 255, 150))
    p.drawPath(path)
    # 2x2 工具方块
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 235))
    for x, y, a in ((34, 34, 0.95), (70, 34, 0.72), (34, 70, 0.72), (70, 94, 0.95)):
        p.setOpacity(a)
        p.drawRoundedRect(x * s, y * s, 24 * s, 24 * s, 7 * s, 7 * s)
    p.setOpacity(1.0)
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------- 安全表达式计算
_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UN_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "pow": pow,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log, "log10": math.log10, "log2": math.log2,
    "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
    "min": min, "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def safe_eval(expression: str) -> float:
    """用 AST 白名单求值，绝不使用 eval，杜绝任意代码执行。"""
    expr = expression.strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    if not expr:
        raise ValueError("请输入表达式")
    tree = ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in _CONSTS:
                return _CONSTS[node.id]
            raise ValueError(f"未知变量：{node.id}")
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UN_OPS:
            return _UN_OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("指数过大")
            value = _BIN_OPS[type(node.op)](left, right)
            if isinstance(value, (int, float)) and abs(value) > 1e100:
                raise ValueError("结果超出范围")
            return value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            if node.keywords:
                raise ValueError("不支持关键字参数")
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError("表达式中包含不支持的语法")

    result = ev(tree)
    if isinstance(result, complex) or not math.isfinite(float(result)):
        raise ValueError("结果无效")
    return result


# ---------------------------------------------------------------- 哈希
HASH_ALGOS = ["MD5", "SHA-1", "SHA-224", "SHA-256", "SHA-384", "SHA-512",
              "SHA3-256", "SHA3-512", "BLAKE2b", "BLAKE2s"]


_HASH_MAP = {
    "MD5": "md5", "SHA-1": "sha1", "SHA-224": "sha224", "SHA-256": "sha256",
    "SHA-384": "sha384", "SHA-512": "sha512",
    "SHA3-256": "sha3_256", "SHA3-512": "sha3_512",
    "BLAKE2b": "blake2b", "BLAKE2s": "blake2s",
}


def _hash_name(algo: str) -> str:
    return _HASH_MAP.get(algo, algo.lower().replace("-", ""))


def hash_text(text: str, algo: str) -> str:
    h = hashlib.new(_hash_name(algo))
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def hash_file(path: str, algo: str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.new(_hash_name(algo))
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
