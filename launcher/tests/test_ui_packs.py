import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication

from netlauncher import localpacks
from netlauncher.auth_ely import Account
from netlauncher.localpacks import LocalPack
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
    while t.elapsed() < ms or (until is not None and not until() and t.elapsed() < 3000):
        QApplication.processEvents()
        if until is not None and until() and t.elapsed() >= ms:
            break


@pytest.fixture
def win(qapp, home, monkeypatch):
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    monkeypatch.setattr("netlauncher.ui.pages.common.confirm_with_option", lambda *a, **k: (True, True))
    ctx = make_context(home, FakeHttp())
    ctx.settings.first_run_done = True
    ctx.accounts.save(Account("Shark", "abc", "tok", "ct"))
    localpacks.save(home, LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", official=True))
    localpacks.save(home, LocalPack("mine", "Выживание", "", "1.21.1", "fabric", "0.16.9"))
    ctx.settings.selected_pack = "mine"
    w = MainWindow(ctx, page_factory=FACTORY)
    w.show()
    pump(30)
    yield w, ctx
    w.close()
    anim.set_enabled(True)


def test_packs_page_lists_installed(win):
    w, ctx = win
    w.open_page("packs")
    page = w.page("packs")
    names = [r.title.text() for r in page.rows]
    assert names == [".NET", "Выживание"]
    assert page.rows[0].tag.isVisibleTo(page.rows[0]) and page.rows[0].tag.text() == "официальная"
    assert not page.rows[1].tag.isVisibleTo(page.rows[1])
    assert page.rows[1].meta.text() == "Fabric 1.21.1"


def test_delete_current_pack_selects_other(win):
    w, ctx = win
    w.open_page("packs")
    page = w.page("packs")
    row = next(r for r in page.rows if r.pack_id == "mine")
    row.delete_btn.click()
    pump(50)
    assert localpacks.get(ctx.lay, "mine") is None
    assert ctx.settings.selected_pack == "net"
    assert [r.pack_id for r in page.rows] == ["net"]


def test_open_folder_opens_game_dir(win, monkeypatch):
    w, ctx = win
    opened = []
    monkeypatch.setattr("netlauncher.ui.pages.packs_page.QDesktopServices.openUrl", lambda url: opened.append(url.toLocalFile()))
    w.open_page("packs")
    w.page("packs").rows[1].folder_btn.click()
    assert Path(opened[0]) == localpacks.game_dir(ctx.lay, "mine")


SECTIONS = {"mods", "resourcepacks", "shaders", "snapshots", "screenshots", "worlds"}


def test_pack_page_sections_for_own_pack(win):
    w, ctx = win
    w.open_pack("mine")
    page = w.page("pack")
    assert set(page.sections) == SECTIONS
    assert all(page.tabs[k].isVisibleTo(page) for k in SECTIONS)
    assert not page.locked_note.isVisibleTo(page)
    assert page.current_section() == "mods" and w.rail.active == "packs"
    assert page.title.text() == "Выживание" and ctx.settings.selected_pack == "mine"


def test_official_pack_is_locked_for_player(win):
    w, ctx = win
    w.open_pack("net")
    page = w.page("pack")
    for k in ("mods", "resourcepacks", "shaders", "snapshots"):
        assert not page.tabs[k].isVisibleTo(page)
    assert page.tabs["screenshots"].isVisibleTo(page) and page.tabs["worlds"].isVisibleTo(page)
    assert page.locked_note.isVisibleTo(page)
    assert page.locked_note.text() == "Сборку собирает автор, менять её нельзя."
    assert page.current_section() == "worlds"
    page.open_section("mods")
    assert page.current_section() == "worlds"


def test_author_can_edit_official(win):
    w, ctx = win
    ctx.settings.author_mode, ctx.settings.github_token = True, "t"
    w.open_pack("net")
    page = w.page("pack")
    assert page.tabs["mods"].isVisibleTo(page) and not page.locked_note.isVisibleTo(page)


def test_switching_pack_resets_mods_page(win):
    w, ctx = win
    localpacks.save(ctx.lay, LocalPack("other", "Другая", "", "1.21.1", "fabric", "0.16.9"))
    mods_dir = localpacks.game_dir(ctx.lay, "other") / "mods"
    mods_dir.mkdir()
    (mods_dir / "bmod.jar").write_bytes(b"not a real jar")
    w.open_pack("mine", "mods")
    mods = w.page("pack").sections["mods"]
    mods.open_browser()
    assert mods.stack.currentWidget() is mods.browser
    w.open_pack("other")
    assert mods.stack.currentWidget() is mods.listing
    pump(until=lambda: len(mods.rows) == 1)
    assert [r.item.name for r in mods.rows] == ["bmod"]
    assert "Другая" in mods.subtitle.text()


def test_packs_row_open_shows_pack_page(win):
    w, ctx = win
    w.open_page("packs")
    w.page("packs").rows[1].open_btn.click()
    assert w.current_page() == "pack" and w.page("pack").pack_id == "mine"


def _png(path, color):
    from PySide6.QtGui import QColor, QImage
    img = QImage(64, 36, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


def test_screenshots_newest_first(qapp, home):
    from netlauncher.ui.pages.screenshots import ScreenshotsView
    from tests.fakes import FakeHttp
    gd = localpacks.game_dir(home, "mine")
    old, new = gd / "screenshots" / "2026-11-01_10.00.00.png", gd / "screenshots" / "2026-11-20_10.00.00.png"
    _png(old, "red")
    _png(new, "blue")
    os.utime(old, (1_000_000, 1_000_000))
    view = ScreenshotsView(make_context(home, FakeHttp()))
    view.show_dir(gd)
    pump(until=lambda: len(view.tiles) == 2)
    assert [tile.path.name for tile in view.tiles] == [new.name, old.name]
    assert view.tiles[0].thumb.pixmap().width() <= 220
    assert any((home.cache / "thumbs").iterdir())


def test_copy_screenshot_to_clipboard(qapp, home):
    from PySide6.QtGui import QGuiApplication
    from netlauncher.ui.pages.screenshots import ScreenshotsView
    from tests.fakes import FakeHttp
    gd = localpacks.game_dir(home, "mine")
    _png(gd / "screenshots" / "a.png", "green")
    view = ScreenshotsView(make_context(home, FakeHttp()))
    view.show_dir(gd)
    pump(until=lambda: len(view.tiles) == 1)
    QGuiApplication.clipboard().clear()
    view.tiles[0].copy()
    img = QGuiApplication.clipboard().image()
    assert not img.isNull() and img.width() == 64


def test_screenshots_empty_state(qapp, home):
    from netlauncher.ui.pages.screenshots import ScreenshotsView
    from tests.fakes import FakeHttp
    view = ScreenshotsView(make_context(home, FakeHttp()))
    view.show_dir(localpacks.game_dir(home, "nothing"))
    pump(50)
    assert view.tiles == [] and view.empty.isVisibleTo(view)
    assert view.empty.text() == "Скриншотов пока нет. Нажми F2 в игре, и скриншот появится здесь."


def test_pack_page_hosts_screenshots(win):
    from netlauncher.ui.pages.screenshots import ScreenshotsView
    w, ctx = win
    _png(localpacks.game_dir(ctx.lay, "mine") / "screenshots" / "s.png", "white")
    w.open_pack("mine", "screenshots")
    view = w.page("pack").sections["screenshots"]
    assert isinstance(view, ScreenshotsView)
    pump(until=lambda: len(view.tiles) == 1)
    assert len(view.tiles) == 1


def test_worlds_view_buttons(win, monkeypatch):
    from netlauncher import worlds
    from netlauncher.ui.pages.worlds import WorldsView
    w, ctx = win
    gd = localpacks.game_dir(ctx.lay, "mine")
    (gd / "saves" / "Остров").mkdir(parents=True)
    (gd / "saves" / "Остров" / "level.dat").write_bytes(b"x")
    w.open_pack("mine", "worlds")
    view = w.page("pack").sections["worlds"]
    assert isinstance(view, WorldsView)
    pump(until=lambda: len(view.rows) == 1)
    row = view.rows[0]
    assert row.title.text() == "Остров"
    row.backup_btn.click()
    pump(until=lambda: len(worlds.backups(ctx.lay, "mine", "Остров")) == 1)
    assert len(worlds.backups(ctx.lay, "mine", "Остров")) == 1
    pump(until=lambda: view.rows and view.rows[0].restore_btn.isEnabled())
    assert view.rows[0].restore_btn.isEnabled()
    played = []
    monkeypatch.setattr(w.page("home"), "play", lambda world=None, server=None: played.append(world))
    view.rows[0].play_btn.click()
    assert played == ["Остров"]
