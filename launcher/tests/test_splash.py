import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtGui import QFontMetrics, QImage
from PySide6.QtWidgets import QApplication

from netlauncher import localpacks
from netlauncher.auth_ely import Account
from netlauncher.localpacks import LocalPack
from netlauncher.ui import anim, theme
from netlauncher.ui.app import make_context
from netlauncher.ui.pages import FACTORY
from netlauncher.ui.window import MainWindow
from tests.fakes import FakeHttp

ICON_DIR = os.path.join(os.path.dirname(__file__), "..", "netlauncher", "ui", "assets", "icon")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


def pump(ms, until=None):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms and not (until and until()):
        QApplication.processEvents()


@pytest.fixture
def win(qapp, home, monkeypatch):
    anim.set_enabled(True)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    ctx = make_context(home, FakeHttp())
    ctx.settings.first_run_done = True
    ctx.accounts.save(Account("Shark", "abc", "tok", "ct"))
    localpacks.save(home, LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", official=True))
    w = MainWindow(ctx, page_factory=FACTORY)
    w.resize(1180, 720)
    w.show()
    pump(50)
    yield w
    w.close()


def test_icon_frames_present():
    for f in range(72):
        img = QImage(os.path.join(ICON_DIR, f"frame_{f:02d}.png"))
        assert img.width() == 256 and img.height() == 256, f
    assert not QImage(os.path.join(ICON_DIR, "icon.png")).isNull()


def test_splash_waits_for_ready_then_finishes(win):
    from netlauncher.ui.splash import Splash
    state = {"ready": False, "done": False}
    s = Splash(win, lambda: state["ready"], speed=4)
    s.finished.connect(lambda: state.update(done=True))
    s.start()
    pump(600)
    assert s.phase == "loading"
    state["ready"] = True
    pump(5000, until=lambda: state["done"])
    assert state["done"] and s.phase == "done"
    assert win.rail.icon_slot.findChild(object, "rail_icon").isVisible()


def test_splash_gives_up_after_8s(win):
    from netlauncher.ui.splash import Splash
    state = {"done": False}
    s = Splash(win, lambda: False, speed=4)
    s.finished.connect(lambda: state.update(done=True))
    s.start()
    pump(4500, until=lambda: state["done"])
    assert state["done"]


def test_brand_texts_share_baseline_and_center(win):
    from netlauncher.ui.splash import Splash
    s = Splash(win, lambda: True, speed=4)
    s.start()
    pump(4000, until=lambda: s.phase == "hold")
    assert s.phase == "hold"
    net, lw = s.net.geometry(), s.lw.geometry()
    assert abs((net.y() + s.net.ascent()) - (lw.y() + s.lw.ascent())) <= 1
    pair_center = (net.left() + lw.right()) / 2
    icon_center = s.icon.geometry().center().x()
    assert abs(pair_center - icon_center) <= 2


def test_net_word_lands_on_title(win):
    from netlauncher.ui.splash import Splash
    state = {"done": False}
    title = win.page("home").panel.title
    s = Splash(win, lambda: True, speed=4)
    s.finished.connect(lambda: state.update(done=True))
    s.start()
    pump(6000, until=lambda: s.phase == "landed")
    assert s.phase in ("landed", "done")
    origin = title.mapTo(win, title.contentsRect().topLeft())
    assert abs(s.net.geometry().x() - origin.x()) <= 2
    assert abs(s.net.text_height() - QFontMetrics(title.font()).height()) <= 3
