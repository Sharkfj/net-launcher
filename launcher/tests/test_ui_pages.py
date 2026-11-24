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


def test_install_reaction(env, monkeypatch):
    w, ctx, gd, confirms = env
    seen = []
    monkeypatch.setattr(w, "skin_react", lambda name: seen.append(name), raising=False)
    w.open_page("mods")
    page = w.page("mods")
    page.open_browser()
    page.browser.query.setText("shoulder")
    page.browser.run_search()
    pump(until=lambda: len(page.browser.cards) == 1)
    page.browser.cards[0].install_btn.click()
    pump(until=lambda: "nod" in seen)
    assert seen == ["check", "nod"]


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
    assert page.repo.isVisibleTo(page) and page.token.isVisibleTo(page)
    assert not hasattr(page, "author_pack")


def test_author_tools_on_official_tab(env):
    w, ctx, gd, _ = env
    w.open_page("official")
    page = w.page("official")
    assert not page.author_box.isVisibleTo(page)
    ctx.settings.author_mode, ctx.settings.github_token = True, "t"
    ctx.settings.github_repo = "owner/packs"
    ctx.http.routes["https://api.github.com/repos/owner/packs"] = {"permissions": {"push": True}}
    w.open_page("home")
    w.open_page("official")
    pump(until=lambda: page.author_box.isVisibleTo(page))
    assert page.author_box.isVisibleTo(page)
    tools = page.author_box
    assert [tools.author_pack.itemText(i) for i in range(tools.author_pack.count())] == [".NET"]
    assert tools.build_btn.text() == "Собрать" and tools.publish_btn.text() == "Опубликовать"


def test_publish_button_says_update_for_catalog_pack(env):
    from netlauncher.catalog import Catalog, PackEntry
    w, ctx, gd, _ = env
    ctx.settings.author_mode, ctx.settings.github_token = True, "t"
    ctx.settings.github_repo = "owner/packs"
    ctx.http.routes["https://api.github.com/repos/owner/packs"] = {"permissions": {"push": True}}
    ctx.catalog = Catalog("0.1.0", {}, [PackEntry("net", ".NET", "", "0.1", "1.21.1", "neoforge", "21.1.267", "u", "")])
    w.open_page("official")
    pump(until=lambda: w.page("official").author_box.isVisible())
    assert w.page("official").author_box.publish_btn.text() == "Обновить сборку"


def test_official_cards_states(env):
    from netlauncher.catalog import Catalog, PackEntry
    w, ctx, gd, _ = env
    localpacks.save(ctx.lay, LocalPack("same", "Same", "1.0", "1.21.1", "fabric", "0.16.9", official=True))
    ctx.catalog = Catalog("0.1.0", {}, [
        PackEntry("net", ".NET", "Киберпанк", "0.2", "1.21.1", "neoforge", "21.1.267", "u", ""),
        PackEntry("same", "Same", "", "1.0", "1.21.1", "fabric", "0.16.9", "u", ""),
        PackEntry("new", "New", "", "0.1", "1.21.1", "fabric", "0.16.9", "u", "")])
    w.open_page("official")
    page = w.page("official")
    assert [(c.entry.id, c.action_btn.text()) for c in page.cards] == [
        ("net", "Обновить"), ("same", "Играть"), ("new", "Установить")]
    assert page.cards[0].desc.text() == "Киберпанк"


def test_about_credits(env):
    w, ctx, gd, _ = env
    page = w.page("settings")
    assert CREDITS == ["@looper_fj"]
    assert page.credits.text() == "Разработчик: @looper_fj"


def test_settings_fields_wide_and_ram_hint_matches(env, monkeypatch):
    w, ctx, gd, _ = env
    page = w.page("settings")
    for f in (page.repo, page.token):
        assert f.minimumWidth() >= 320
    from netlauncher.ui.pages.settings_page import gb_text
    assert gb_text(7680) == "7,5 ГБ" and gb_text(8192) == "8 ГБ"


def test_browser_source_switch_with_personal_key(env, monkeypatch):
    w, ctx, gd, _ = env
    w.open_page("mods")
    page = w.page("mods")
    page.open_browser()
    page.browser.set_source("curseforge")
    assert page.browser.source == "modrinth"
    assert page.browser.status.text() == "Для поиска на CurseForge укажи сервер друзей или свой ключ API в настройках."
    ctx.settings.curseforge_key = "KEY"
    from netlauncher.curseforge import API as CF
    ctx.http.routes[f"{CF}/mods/search"] = {"data": [{"id": 7, "name": "Chromeware", "slug": "c", "summary": "s",
                                                     "downloadCount": 1500, "logo": None, "links": {}}]}
    page.browser.set_source("curseforge")
    assert page.browser.source == "curseforge"
    pump(until=lambda: len(page.browser.cards) == 1)
    assert page.browser.cards[0].title.text() == "Chromeware" and page.browser.cards[0].meta.text() == "2 тыс. загрузок"


def test_settings_has_no_theme_row(env):
    from PySide6.QtWidgets import QLabel
    w, ctx, gd, _ = env
    page = w.page("settings")
    assert not hasattr(page, "theme_chips") and not hasattr(page, "set_theme")
    assert "Тема" not in [lb.text() for lb in page.findChildren(QLabel)]


def _hit(i):
    return {"project_id": f"p{i}", "slug": f"p{i}", "title": f"Mod {i}", "description": "d", "downloads": i,
            "icon_url": "", "project_type": "mod", "client_side": "required", "server_side": "optional"}


def test_catalog_sort_category_and_more(env):
    w, ctx, gd, _ = env
    ctx.http.routes[f"{API}/tag/category"] = [{"name": "technology", "project_type": "mod", "header": "categories"}]
    ctx.http.routes[f"{API}/search"] = lambda c: {"hits": [_hit(int(c.params["offset"]) + i) for i in range(20)]}
    w.open_page("mods")
    page = w.page("mods")
    page.open_browser()
    b = page.browser
    pump(until=lambda: len(b.cards) == 20 and b.category.count() == 2)
    assert [b.category.itemText(i) for i in range(b.category.count())] == ["Все категории", "Technology"]
    b.set_sort("newest")
    pump(until=lambda: ctx.http.calls[-1].params.get("index") == "newest" and len(b.cards) == 20)
    b.category.setCurrentIndex(1)
    pump(until=lambda: ["categories:technology"] in json.loads(ctx.http.calls[-1].params["facets"]))
    pump(until=lambda: len(b.cards) == 20)
    assert b.more_btn.isVisibleTo(b)
    b.more_btn.click()
    pump(until=lambda: len(b.cards) == 40)
    assert ctx.http.calls[-1].params["offset"] == 20 and b.cards[39].title.text() == "Mod 39"


def test_detail_panel_info_and_deps(env):
    w, ctx, gd, _ = env
    dep = {"id": "dep-1", "project_id": "dep", "version_number": "1", "version_type": "release",
           "game_versions": ["1.21.1"], "loaders": ["neoforge"], "date_published": "2026-01-01", "dependencies": [],
           "files": [{"url": "https://cdn/dep.jar", "filename": "dep.jar", "primary": True, "size": len(MINE) + 1,
                      "hashes": {"sha1": sha1(b"dep"), "sha512": sha512(b"dep")}}]}
    ver = json.loads(json.dumps(ctx.http.routes[f"{API}/project/shoulder/version"]))
    ver[0]["dependencies"] = [{"project_id": "dep", "dependency_type": "required"}]
    ctx.http.routes[f"{API}/project/shoulder/version"] = ver
    ctx.http.routes[f"{API}/project/dep/version"] = [dep]
    ctx.http.downloads["https://cdn/dep.jar"] = b"dep"
    ctx.http.routes[f"{API}/projects"] = lambda c: [
        {"id": i, "slug": i, "title": {"shoulder": "Shoulder Surfing", "dep": "Dep Lib"}[i], "description": "",
         "downloads": 1, "icon_url": "", "project_type": "mod", "client_side": "required", "server_side": "optional"}
        for i in json.loads(c.params["ids"])]
    ctx.http.routes[f"{API}/project/shoulder"] = {
        "id": "shoulder", "slug": "shoulder", "title": "Shoulder Surfing", "description": "Камера из-за плеча",
        "body": "## Как это работает\nКамера сдвигается вбок.", "downloads": 100, "followers": 2,
        "categories": ["utility"], "icon_url": "", "gallery": [{"url": "https://i/1.png", "title": "Вид"}]}
    ctx.http.routes[f"{API}/project/shoulder/members"] = [{"role": "Owner", "user": {"username": "Exopandora"}}]
    w.open_page("mods")
    page = w.page("mods")
    page.open_browser()
    b = page.browser
    pump(until=lambda: len(b.cards) == 1)
    b.cards[0].select()
    panel = b.detail
    pump(until=lambda: panel.deps.text().startswith("Вместе с ним") and panel.meta.text().startswith("Exopandora"))
    assert panel.isVisibleTo(b) and panel.title.text() == "Shoulder Surfing"
    assert panel.meta.text().startswith("Exopandora")
    assert "Камера сдвигается вбок." in panel.body.toPlainText()
    assert len(panel.thumbs) == 1
    assert panel.deps.text() == "Вместе с ним установятся: Dep Lib."
    panel.install_btn.click()
    pump(until=lambda: (gd / "mods" / "ss.jar").exists() and (gd / "mods" / "dep.jar").exists())
    assert (gd / "mods" / "dep.jar").exists()


def test_richtext_loads_remote_image(qapp, home):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument
    from netlauncher.ui.richtext import RichText
    from tests.test_skin import _two_tone_png
    http = FakeHttp(downloads={"https://i/x.png": _two_tone_png()})
    rt = RichText(http, home.cache)
    rt.resize(500, 400)
    rt.show()
    rt.set_markdown("Текст\n\n![x](https://i/x.png)")
    pump(until=lambda: rt.loaded("https://i/x.png"))
    img = rt.document().resource(QTextDocument.ResourceType.ImageResource, QUrl("https://i/x.png"))
    assert img is not None and not img.isNull()


def test_mods_page_for_vanilla_pack(env):
    w, ctx, gd, _ = env
    localpacks.save(ctx.lay, LocalPack("vanilla", "Чистый", "0.0", "1.21.1", "vanilla", ""))
    ctx.settings.selected_pack = "vanilla"
    w.open_page("mods")
    page = w.page("mods")
    assert page.subtitle.text() == "В сборке без загрузчика моды не работают. Создай сборку с Fabric, Forge или NeoForge."
    assert not page.find_btn.isVisibleTo(page)


FBASE = "https://friends.example.net"


def _friends_routes(http, state):
    from netlauncher.friends import ELY_JOIN
    http.routes.update({f"{FBASE}/v1/auth/challenge": {"server_id": "sid"}, ELY_JOIN: None,
                        f"{FBASE}/v1/auth/verify": {"token": "S", "name": "Shark"},
                        f"{FBASE}/v1/state": state, f"{FBASE}/v1/presence": state})
    for p in ("friends/request", "friends/accept", "friends/decline", "friends/remove", "invite",
              "invite/dismiss"):
        http.routes[f"{FBASE}/v1/{p}"] = state


STATE = {"me": "Shark", "friends": [
    {"name": "Vasya", "online": True, "status": "playing", "pack": ".NET", "server": "play.example.net",
     "last_seen": 1},
    {"name": "Oleg", "online": False, "status": "", "pack": "", "server": "", "last_seen": 0}],
    "incoming": ["Petya"], "outgoing": ["Masha"],
    "invites": [{"from": "Vasya", "pack": ".NET", "server": "play.example.net", "created": 1}]}


def test_friends_not_configured_hint(env):
    w, ctx, gd, _ = env
    w.open_page("friends")
    page = w.page("friends")
    assert page.notice.text().startswith("Сервер друзей не подключён.")


def test_friends_list_requests_invites(env, monkeypatch):
    w, ctx, gd, _ = env
    ctx.settings.friends_url = FBASE
    _friends_routes(ctx.http, STATE)
    played = {}
    monkeypatch.setattr(w.page("home"), "play", lambda world=None, server=None: played.setdefault("server", server))
    w.open_page("friends")
    page = w.page("friends")
    pump(until=lambda: len(page.rows) == 2)
    assert page.subtitle.text() == "1 в сети"
    vasya, oleg = page.rows
    assert vasya.status.text() == "Играет в .NET на play.example.net" and vasya.join_btn.isVisibleTo(vasya)
    assert oleg.status.text() == "Не в сети" and not oleg.join_btn.isVisibleTo(oleg)
    assert [r.name for r in page.request_rows] == ["Petya"] and page.outgoing.text() == "Ждут ответа: Masha"
    page.request_rows[0].accept_btn.click()
    pump(until=lambda: any(c.url.endswith("/friends/accept") for c in ctx.http.calls))
    assert next(c for c in ctx.http.calls if c.url.endswith("/friends/accept")).body == {"name": "Petya"}
    assert page.invite_rows[0].text.text() == "Vasya зовёт играть в .NET"
    page.invite_rows[0].play_btn.click()
    pump(until=lambda: "server" in played)
    assert played["server"] == "play.example.net" and w.current_page() == "home"


def test_add_friend_and_presence(env):
    w, ctx, gd, _ = env
    ctx.settings.friends_url = FBASE
    _friends_routes(ctx.http, {**STATE, "friends": [], "incoming": [], "outgoing": [], "invites": []})
    w.open_page("friends")
    page = w.page("friends")
    page.add_name.setText("Vasya")
    page.add_btn.click()
    pump(until=lambda: any(c.url.endswith("/friends/request") for c in ctx.http.calls))
    assert next(c for c in ctx.http.calls if c.url.endswith("/friends/request")).body == {"name": "Vasya"}
    w.game_status = ("playing", ".NET", "play.example.net")
    page.tick()
    playing = lambda: [c for c in ctx.http.calls
                       if c.url.endswith("/v1/presence") and (c.body or {}).get("status") == "playing"]
    pump(until=lambda: playing())
    assert playing()[-1].body == {"status": "playing", "pack": ".NET", "server": "play.example.net"}


def test_friend_status_text():
    from netlauncher.ui.pages.friends_page import status_text
    import time as _t
    assert status_text({"online": True, "status": "launcher"}) == "В сети, в лаунчере"
    assert status_text({"online": True, "status": "playing", "pack": ".NET", "server": ""}) == "Играет в .NET"
    assert status_text({"online": False, "last_seen": _t.time() - 7200}) == "Не в сети, был 2 ч назад"


def test_richtext_protocol_relative_image(qapp, home):
    from netlauncher.ui.richtext import RichText
    from tests.test_skin import _two_tone_png
    http = FakeHttp(downloads={"https://media.forgecdn.net/a.png": _two_tone_png()})
    rt = RichText(http, home.cache)
    rt.show()
    rt.set_html('<p>x <img src="//media.forgecdn.net/a.png"></p>')
    pump(until=lambda: rt.loaded("https://media.forgecdn.net/a.png"))
    assert rt.loaded("https://media.forgecdn.net/a.png")


def test_backgrounds_toggle_plain_scene(env):
    from netlauncher.settings import load_settings
    w, ctx, gd, _ = env
    before = w.scene.kind
    page = w.page("settings")
    page.backgrounds.click()
    assert w.scene.kind == "plain" and ctx.settings.backgrounds is False
    assert load_settings(ctx.lay.settings_file).backgrounds is False
    page.backgrounds.click()
    assert w.scene.kind == before and before != "plain"


def test_settings_shortcut_button(env, monkeypatch):
    from pathlib import Path
    w, ctx, gd, _ = env
    made = []
    monkeypatch.setattr("netlauncher.shortcut.create", lambda cmd, icon, name=".NET Launcher": made.append(cmd) or Path("/x"))
    page = w.page("settings")
    page.shortcut_btn.click()
    assert len(made) == 1
    assert w.toast_widget.text.text() == "Ярлык на рабочем столе создан"


def test_author_tools_require_repository_write_access(env):
    w, ctx, _, _ = env
    ctx.settings.author_mode = True
    ctx.settings.github_repo, ctx.settings.github_token = "owner/packs", "read-only"
    ctx.http.routes["https://api.github.com/repos/owner/packs"] = {"permissions": {"push": False}}
    w.open_page("official")
    pump(until=lambda: any(call.url.endswith("/repos/owner/packs") for call in ctx.http.calls))
    assert not w.page("official").author_box.isVisible()


def test_curseforge_tab_enabled_with_proxy(env):
    w, ctx, _, _ = env
    ctx.settings.friends_url = FBASE
    _friends_routes(ctx.http, STATE)
    ctx.http.routes[FBASE + "/cf/mods/search"] = {"data": [{"id": 42, "name": "Via proxy"}]}
    ctx.http.routes[FBASE + "/cf/categories"] = {"data": []}
    w.open_page("mods")
    page = w.page("mods")
    page.open_browser()
    page.browser.set_source("curseforge")
    pump(until=lambda: any(c.title.text() == "Via proxy" for c in page.browser.cards))
    assert page.browser.source == "curseforge" and page.browser.cards[0].title.text() == "Via proxy"
