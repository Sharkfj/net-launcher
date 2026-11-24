"""Export the app icon (netlauncher/ui/assets/icon/icon.png, rendered by tools/render_icon.py) to PNG and ICO."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from netlauncher.ui.icons import app_icon  # noqa: E402

app = QGuiApplication([])
here = Path(__file__).parent
pm = app_icon(256).pixmap(QSize(256, 256))
pm.save(str(here / "icon.png"))
pm.save(str(here / "icon.ico"))
print("ok")
