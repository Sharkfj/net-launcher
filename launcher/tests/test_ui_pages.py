import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication

from netlauncher import localpacks, snapshots
from netlauncher.auth_ely import Account
from netlauncher.localpacks import LocalPack
from netlauncher.modrinth import API
from netlauncher.pack import save_state
from netlauncher.ui import anim, theme
from netlauncher.ui.app import CREDITS, make_context
from netlauncher.ui.pages import FACTORY
from netlauncher.ui.pages import common
from netlauncher.ui.window import MainWindow
from tests.fakes import FakeHttp, sha1, sha512
from tests.jars import jar_bytes, toml_for

CLOTH = jar_bytes(toml=toml_for("cloth_config", "Cloth Config"))
FOG = jar_bytes(toml=toml_for("fog", "Fog"))
MINE = jar_bytes(toml=toml_for("mymod", "Мой мод"))
NEW = jar_bytes(toml=toml_for("shouldersurfing", "Shoulder Surfing"))


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


def pump(ms=0, until=None):
    t = QElapsedTimer()
    t.start()
    while True:
        QApplication.processEvents()
        if t.elapsed() >= ms and (until is None or until() or t.elapsed() > 3000):
            break


@pytest.fixture
def env(qapp, home, monkeypatch):
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    gd = home.instances / "net"
    (gd / "mods").mkdir(parents=True)
    (gd / "mods" / "cloth.jar").write_bytes(CLOTH)
    (gd / "mods" / "fog.jar.disabled").write_bytes(FOG)
    (gd / "mods" / "mine.jar").write_bytes(MINE)
    save_state(gd, {"version": "0.1", "files": {
        "mods/cloth.jar": {"sha1": sha1(CLOTH), "client": "required", "server": "required", "project": ""},
        "mods/fog.jar": {"sha1": sha1(FOG), "client": "required", "server": "unsupported", "project": ""}}})
    localpacks.save(home, LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267"))
    nv = {"id": "ss-5", "project_id": "shoulder", "version_number": "5", "version_type": "release",
          "game_versions": ["1.21.1"], "loaders": ["neoforge"], "date_published": "2026-11-10", "dependencies": [],
          "files": [{"url": "https://cdn/ss.jar", "filename": "ss.jar", "primary": True, "size": len(NEW),
                     "hashes": {"sha1": sha1(NEW), "sha512": sha512(NEW)}}]}
    proj = {"id": "shoulder", "project_id": "shoulder", "slug": "shoulder", "title": "Shoulder Surfing",
            "description": "Камера из-за плеча", "downloads": 12988728, "icon_url": "", "project_type": "mod",
            "client_side": "required", "server_side": "unsupported"}
    http = FakeHttp({f"{API}/version_files": {}, f"{API}/version_files/update": {},
                     f"{API}/search": {"hits": [proj]}, f"{API}/projects": [proj],
                     f"{API}/project/shoulder/version": [nv]}, downloads={"https://cdn/ss.jar": NEW})
    ctx = make_context(home, http)
    ctx.settings.first_run_done = True
    ctx.accounts.save(Account("Shark", "abc", "tok", "ct"))
    confirms = []
    monkeypatch.setattr(common, "confirm", lambda parent, title, text, ok: (confirms.append(text), True)[1])
    w = MainWindow(ctx, page_factory=FACTORY)
    w.show()
    pump(30)
    yield w, ctx, gd, confirms
    anim.set_enabled(True)


def test_content_lists_and_filters(env):
    w, ctx, gd, _ = env
    w.open_page("mods")
    page = w.page("mods")
    pump(until=lambda: len(page.rows) == 3)
    assert [r.item.name for r in page.rows] == ["Cloth Config", "Fog", "Мой мод"]
    assert page.subtitle.text() == "3 мода в сборке «.NET»"
    page.set_filter("disabled")
    assert [r.item.name for r in page.visible_rows()] == ["Fog"]
    page.set_filter("all")
    page.search.setText("мой")
    assert [r.item.name for r in page.visible_rows()] == ["Мой мод"]
    assert [r.badge.text() for r in page.rows] == ["сборка", "сборка", "моё"]


def test_locked_toggle_disabled(env):
    w, ctx, gd, _ = env
    w.open_page("mods")
    page = w.page("mods")
    pump(until=lambda: len(page.rows) == 3)
    cloth, fog, mine = page.rows
    assert not cloth.toggle.isEnabled() and cloth.toggle.toolTip() == "Нужен на сервере, выключить нельзя"
    assert fog.toggle.isEnabled() and not fog.toggle.isChecked()
    mine.toggle.click()
    pump(until=lambda: (gd / "mods" / "mine.jar.disabled").exists())
    assert (gd / "mods" / "mine.jar.disabled").exists()


def test_install_flow_shows_plan(env):
    w, ctx, gd, confirms = env
    w.open_page("mods")
    page = w.page("mods")
    page.open_browser()
    page.browser.query.setText("shoulder")
    page.browser.run_search()
    pump(until=lambda: len(page.browser.cards) == 1)
    card = page.browser.cards[0]
    assert card.title.text() == "Shoulder Surfing" and card.meta.text() == "13 млн загрузок"
    card.install_btn.click()
    pump(until=lambda: (gd / "mods" / "ss.jar").exists())
    assert confirms and confirms[0] == "Будет установлено: Shoulder Surfing."
    assert (gd / "mods" / "ss.jar").exists()


def test_snapshot_restore_confirm(env):
    w, ctx, gd, confirms = env
    root = ctx.lay.snapshots / "net"
    snap = snapshots.create(root, gd, "Установка: Fog")
    (gd / "mods" / "mine.jar").unlink()
    w.open_page("snapshots")
    page = w.page("snapshots")
    pump(until=lambda: len(page.rows) == 1)
    page.rows[0].restore_btn.click()
    pump(until=lambda: (gd / "mods" / "mine.jar").exists())
    assert (gd / "mods" / "mine.jar").exists()
    assert confirms[-1].startswith("Вернуть моды и настройки к состоянию на ")
    assert confirms[-1].endswith("Текущее состояние сохранится отдельным снимком.")


def test_settings_ram_persist(env):
    w, ctx, gd, _ = env
    w.open_page("settings")
    page = w.page("settings")
    page.ram.setValue(6144)
    assert page.ram_label.text() == "6 ГБ"
    from netlauncher.settings import load_settings
    assert load_settings(ctx.lay.settings_file).max_ram_mb == 6144
    page.animations.click()
    assert load_settings(ctx.lay.settings_file).animations is False


def test_author_section_hidden_when_off(env):
    w, ctx, gd, _ = env
    w.open_page("settings")
    page = w.page("settings")
    assert not page.author_box.isVisibleTo(page)
    page.author_toggle.click()
    assert page.author_box.isVisibleTo(page)
    assert [page.author_pack.itemText(i) for i in range(page.author_pack.count())] == [".NET"]


def test_about_credits(env):
    w, ctx, gd, _ = env
    page = w.page("settings")
    assert CREDITS == ["@looper_fj", "Claude Code"]
    assert page.credits.text() == "Разработчики: @looper_fj и Claude Code"


def test_settings_fields_wide_and_ram_hint_matches(env, monkeypatch):
    w, ctx, gd, _ = env
    page = w.page("settings")
    for f in (page.repo, page.token, page.pack_desc, page.pack_server):
        assert f.minimumWidth() >= 320
    from netlauncher.ui.pages.settings_page import gb_text
    assert gb_text(7680) == "7,5 ГБ" and gb_text(8192) == "8 ГБ"


def test_browser_source_switch_requires_key(env, monkeypatch):
    w, ctx, gd, _ = env
    w.open_page("mods")
    page = w.page("mods")
    page.open_browser()
    page.browser.set_source("curseforge")
    assert page.browser.source == "modrinth"
    assert page.browser.status.text() == "Чтобы искать на CurseForge, добавь ключ API в настройках, раздел «Лаунчер»."
    ctx.settings.curseforge_key = "KEY"
    from netlauncher.curseforge import API as CF
    ctx.http.routes[f"{CF}/mods/search"] = {"data": [{"id": 7, "name": "Chromeware", "slug": "c", "summary": "s",
                                                     "downloadCount": 1500, "logo": None, "links": {}}]}
    page.browser.set_source("curseforge")
    assert page.browser.source == "curseforge"
    pump(until=lambda: len(page.browser.cards) == 1)
    assert page.browser.cards[0].title.text() == "Chromeware" and page.browser.cards[0].meta.text() == "2 тыс. загрузок"


def test_settings_theme_switch(env):
    w, ctx, gd, _ = env
    page = w.page("settings")
    assert w.theme == "glass" and page.theme_chips["glass"].active
    page.set_theme("solid")
    assert w.theme == "solid" and ctx.settings.theme == "solid" and page.theme_chips["solid"].active
    page.set_theme("glass")
    assert w.theme == "glass"
