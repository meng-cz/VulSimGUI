# main.py
import sys
import os
from pathlib import Path

def resource_path(rel: str) -> Path:
    """
    兼容源码运行 & PyInstaller 打包运行
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parent / rel

# Windows + 源码运行时才需要显式 add_dll_directory
if sys.platform == "win32" and not getattr(sys, "frozen", False):
    import PyQt6
    qt_bin = Path(PyQt6.__file__).resolve().parent / "Qt6" / "bin"
    os.add_dll_directory(str(qt_bin))

import resources_rc  # 注册 Qt 资源

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

QSS_PATH = resource_path("ui/theme.qss")

def main():
    app = QApplication(sys.argv)
    try:
        app.setStyleSheet(QSS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] Failed to load QSS: {QSS_PATH} -> {e}")

    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
