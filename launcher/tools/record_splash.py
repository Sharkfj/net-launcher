"""Render the real startup sequence into the English README preview."""
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "launcher"))

from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from netlauncher import catalog, i18n, localpacks
from netlauncher.auth_ely import offline_account
from netlauncher.paths import layout
from netlauncher.ui import anim, theme
from netlauncher.ui.app import make_context
from netlauncher.ui.pages import FACTORY
from netlauncher.ui.splash import Splash
from netlauncher.ui.window import MainWindow


def capture(directory):
    demo = catalog.parse(json.loads((ROOT / "catalog.json").read_text(encoding="utf-8")))
    entry = demo.get("net")
    entry.description = "A Create-powered cyberpunk world of corporations, implants and trains."
    entry.changelog = "First release of the .NET modpack."
    preview_catalog = Path(directory) / "catalog.json"
    preview_catalog.write_text(json.dumps(catalog.to_json(demo)), encoding="utf-8")
    os.environ["NET_LAUNCHER_CATALOG"] = str(preview_catalog)
    app = QApplication([])
    theme.apply(app)
    i18n.set_language("en")
    anim.set_enabled(True)
    ctx = make_context(layout(directory), None)
    ctx.settings.first_run_done = ctx.settings.shortcut_asked = True
    ctx.accounts.save(offline_account("Player"))
    localpacks.save(ctx.lay, localpacks.from_entry(entry))
    window = MainWindow(ctx, page_factory=FACTORY)
    window.show()
    frames = []

    def grab():
        img = window.grab().toImage().scaledToWidth(680, Qt.TransformationMode.SmoothTransformation)
        rgb = img.convertToFormat(QImage.Format.Format_RGB888)
        frames.append(Image.frombytes("RGB", (rgb.width(), rgb.height()), bytes(rgb.constBits()),
                                      "raw", "RGB", rgb.bytesPerLine()))

    ended = []
    splash = Splash(window, lambda: window.page("home").startup_done)
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.timeout.connect(grab)

    def finish():
        timer.stop()
        grab()
        ended.append(True)
        app.quit()

    splash.finished.connect(finish)
    splash.start()
    grab()
    timer.start(33)
    QTimer.singleShot(20000, app.quit)
    app.exec()
    if not ended:
        raise RuntimeError("Splash did not finish")
    return frames


def write_gif(frames, dest):
    # A common palette keeps stationary gradients from flickering between frames.
    samples = frames[::8] + frames[-1:]
    swatches = Image.new("RGB", (168, 104 * len(samples)))
    for index, frame in enumerate(samples):
        swatches.paste(frame.resize((168, 104)), (0, index * 104))
    palette = swatches.quantize(192)
    indexed = [img.quantize(palette=palette, dither=Image.Dither.NONE) for img in frames]
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = [30 if i % 3 != 2 else 40 for i in range(len(frames))]
    duration[-1] = 1000
    indexed[0].save(dest, save_all=True, append_images=indexed[1:], duration=duration, loop=0, optimize=True)
    if dest.stat().st_size > 5_000_000:
        raise RuntimeError("GIF exceeds 5 MB")


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        frames = capture(directory)
        write_gif(frames, ROOT / "docs" / "images" / "launcher-startup.gif")
