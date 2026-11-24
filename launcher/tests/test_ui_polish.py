import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication

import netlauncher
from netlauncher import localpacks
from netlauncher.auth_ely import Account
from netlauncher.localpacks import LocalPack
from netlauncher.modrinth import API
from netlauncher.ui import anim, theme
from netlauncher.ui.app import make_context
from netlauncher.ui.pages import FACTORY
from netlauncher.ui.window import MainWindow
from tests.fakes import FakeHttp


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


def pump(ms=0, until=None):
    t = QElapsedTimer()
    t.start()
    while True:
        QApplication.processEvents()
        if t.elapsed() >= ms and (until is None or until() or t.elapsed() > 4000):
            break


@pytest.fixture
def win(qapp, home, monkeypatch):
    anim.set_enabled(True)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    hits = [{"project_id": f"p{i}", "slug": f"p{i}", "title": f"Mod {i}", "description": "d", "downloads": 5,
             "icon_url": "", "project_type": "mod", "client_side": "required", "server_side": "optional"}
            for i in range(3)]
    ctx = make_context(home, FakeHttp({f"{API}/search": {"hits": hits}, f"{API}/tag/category": [],
                                       f"{API}/version_files": {}}))
    ctx.settings.first_run_done = True
    ctx.accounts.save(Account("Shark", "abc", "tok", "ct"))
    localpacks.save(home, LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267"))
    w = MainWindow(ctx, page_factory=FACTORY)
    w.resize(1180, 720)
    w.show()
    pump(100)
    yield w
    w.close()


def test_toast_shows_and_hides(win):
    win.toast("Готово")
    assert win.toast_widget.isVisible() and win.toast_widget.text.text() == "Готово"
    pump(3800)
    assert not win.toast_widget.isVisible()


def test_selected_card_marked(win):
    win.open_page("mods")
    page = win.page("mods")
    page.open_browser()
    b = page.browser
    pump(until=lambda: len(b.cards) == 3)
    b.cards[1].select()
    assert [c.selected for c in b.cards] == [False, True, False]
    b.cards[2].select()
    assert [c.selected for c in b.cards] == [False, False, True]


def test_friends_online_badge(win):
    page = win.page("friends")
    page._show({"me": "Shark", "friends": [
        {"name": "A", "online": True, "status": "launcher", "pack": "", "server": "", "last_seen": time.time()},
        {"name": "B", "online": False, "status": "", "pack": "", "server": "", "last_seen": 0}],
        "incoming": ["C"], "outgoing": [], "invites": []})
    assert win.nav_button("friends").badge == "1"
    page._show({"me": "Shark", "friends": [], "incoming": [], "outgoing": [], "invites": []})
    assert win.nav_button("friends").badge == ""


def test_version_in_rail(win):
    assert win.rail.version.text() == f"v{netlauncher.__version__}"


def test_search_fields_have_icon(win):
    page = win.page("mods")
    assert page.search.actions() and page.browser.query.actions()


def test_search_icon_fills_its_box(qapp):
    from PySide6.QtCore import QSize
    from netlauncher.ui.widgets import search_field
    f = search_field("x")
    img = f.actions()[0].icon().pixmap(QSize(16, 16)).toImage()
    xs = [x for x in range(img.width()) for y in range(img.height()) if img.pixelColor(x, y).alpha() > 40]
    assert max(xs) - min(xs) + 1 >= 0.75 * img.width()


def test_horizontal_scrollbar_styled():
    css = theme.qss()
    assert "QScrollBar:horizontal" in css and "QScrollBar::handle:horizontal" in css
