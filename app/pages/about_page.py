"""关于页。"""
from ..glass import PageScaffold, GlassCard, GlassButton, label
from .. import __version__


class AboutPage(PageScaffold):
    def __init__(self, parent=None):
        super().__init__("关于 LumiBox", "版本信息、技术栈与使用说明", parent)

        card = GlassCard("LumiBox · Windows 综合工具箱", f"版本 {__version__}", spacing=10)
        card.add(label("一个采用液态玻璃（Liquid Glass）视觉语言的本地桌面工具集合，"
                       "把日常最常用的系统、文本、图片与网络小工具收进同一个窗口。", 11))
        card.add(label("设计原则：离线优先 · 数据不出本机 · 所有功能真实可用", 10, False, True))
        self.add_card(card)

        stack = GlassCard("技术栈", "", spacing=10)
        for name, desc in [
            ("PySide6 / Qt 6", "界面框架，全部控件自绘实现玻璃质感与流体渐变"),
            ("psutil", "CPU、内存、磁盘、网络与进程信息"),
            ("Pillow", "图片压缩、缩放、格式转换、取色与截图"),
            ("qrcode / zxing-cpp", "离线二维码生成与本地图片解析"),
            ("python-pptx / PyMuPDF", "PDF→PPTX 渲染、PPTX→PDF（LibreOffice 可选）"),
            ("marshal / dis / zlib", "pyc 字节码反汇编与 PyInstaller 归档提取"),
            ("cryptography", "密码保险箱 AES 加密（Fernet + PBKDF2 48 万次）"),
            ("PyYAML / tomli-w / markdown / weasyprint", "格式互转、Markdown 渲染与 PDF 导出"),
            ("pytesseract / openpyxl", "OCR 文字识别与 CSV↔Excel 互转（自动探测）"),
            ("标准库 hashlib / winreg / socket", "文件去重、粉碎、启动项、端口扫描"),
        ]:
            row = label(f"•  {name}  —  {desc}", 10)
            stack.add(row)
        self.add_card(stack)

        pack = GlassCard("打包成 .exe", "", spacing=10)
        pack.add(label("项目根目录已提供 build.bat，在 Windows 上双击即可一键打包：", 10))
        code = label("python -m pip install -r requirements.txt\n"
                     "build.bat     （已内含全部 hidden-import / collect-submodules 参数）", 9, True)
        code.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace; padding: 6px;")
        pack.add(code)
        pack.add(label("产物位于 dist\\LumiBox.exe，为单文件绿色程序，可直接拷贝到任意 Windows 电脑运行。", 10, False, True))
        pack.add(label("若杀毒软件误报，可改用 --onedir 模式或添加白名单；首次启动单文件模式会稍慢，属正常现象。", 9, False, True))
        self.add_card(pack)

        keys = GlassCard("快捷键", "", spacing=8)
        keys.add(label("Ctrl + 1 ~ 9 — 切换左侧前九个页面", 10))
        keys.add(label("Ctrl + ` — 隐藏到系统托盘 / 恢复窗口    Ctrl + Alt + S — 快速截图", 10))
        keys.add(label("拖拽标题栏 — 移动窗口    双击标题栏 — 最大化 / 还原", 10))
        keys.add(label("计算器页面：输入框中按回车即可得到结果", 10))
        keys.add(label("系统增强页：窗口置顶、透明度调整、系统托盘与全局热键", 10))
        keys.add(label("右下角可拖拽调整窗口大小", 10))
        self.add_card(keys)

        extra_card = GlassCard("关于新增功能", "", spacing=8)
        extra_card.add(label("· 反编译工具内置 CPython dis 反汇编与 PyInstaller CArchive/PYZ 归档提取，"
                             "格式思路参考 GitHub 开源项目 pyinstxtractor，代码为独立实现。", 9))
        extra_card.add(label("· 可选安装 uncompyle6 / decompyle3 / pycdc 后可在页面内调用还原源码；"
                             "请仅分析自有或已获授权的文件。", 9))
        extra_card.add(label("· PDF→PPTX 为「每页高清图片」方案，版式保真但文字不可编辑；"
                             "PPT / PPTX → PDF 的完整版式需要本机安装免费的 LibreOffice。", 9))
        extra_card.add(label("· 局域网扫描使用 ping + ARP 表 + 反向 DNS，无需管理员权限；"
                             "磁盘 S.M.A.R.T. 详细数据在部分系统需管理员权限。", 9))
        extra_card.add(label("· OCR 需本机安装 tesseract-ocr（中文识别另装 chi_sim 语言包）；"
                             "未安装时界面会给出提示，PDF 文本层提取不依赖 OCR 引擎。", 9))
        extra_card.add(label("· hosts 写入、启动项/服务修改、定时关机均需相应权限；"
                             "hosts 每次保存自动备份到 ~/.lumibox/hosts_backup。", 9))
        extra_card.add(label("· 文件粉碎对 SSD / 日志型文件系统不保证物理不可恢复；"
                             "密码保险箱主密码丢失后无法找回，请妥善保管。", 9))
        self.add_card(extra_card)
        self.add_stretch(1)
