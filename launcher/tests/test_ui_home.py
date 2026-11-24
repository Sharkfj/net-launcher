import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import time

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication

from netlauncher import localpacks
from netlauncher.auth_ely import AUTH, Account
from netlauncher.catalog import Catalog, PackEntry
from netlauncher.localpacks import LocalPack
from netlauncher.net import HttpError
from netlauncher.ui import anim, theme
from netlauncher.ui.app import make_context
from netlauncher.ui.pages import FACTORY
from netlauncher.ui.window import MainWindow
from tests.fakes import FakeHttp


@pytest.fixture(scope="session")
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


def err(status, msg):
    return HttpError(status, "x", json.dumps({"errorMessage": msg}))


def test_version_lists_fit_seven_rows_and_keep_keyboard_navigation(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from netlauncher.ui.pages.home import CreatePanel

    panel = CreatePanel()
    panel.show()
    panel.activateWindow()
    assert QTest.qWaitForWindowExposed(panel)
    try:
        for combo in (panel.version, panel.loader_version):
            combo.blockSignals(True)
            combo.addItems([str(i) for i in range(300)])
            combo.showPopup()
            qapp.processEvents()
            view = combo.view()
            assert view.window().height() <= 7 * view.sizeHintForRow(0) + 32
            assert view.viewport().rect().contains(view.visualRect(view.model().index(6, 0)))
            assert view.verticalScrollBar().isVisible()
            QTest.keyClick(view, Qt.Key.Key_Down)
            QTest.keyClick(view, Qt.Key.Key_Return)
            assert combo.currentText() == "1"
            assert not view.isVisible()
    finally:
        panel.close()


class FakeProcess:
    def __init__(self, game_dir):
        self.game_dir = game_dir
        self.log_path = game_dir / "logs" / "latest.log"
        self.code = None
        self.cmd = None

    def start(self, cmd, cwd):
        self.cmd = cmd
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")

    def poll(self):
        return self.code


@pytest.fixture
def make(qapp, home, monkeypatch):
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)

    def build(http=None, account=True, pack=True, catalog=None):
        http = http or FakeHttp({f"{AUTH}/validate": None})
        ctx = make_context(home, http)
        ctx.settings.first_run_done = True
        if account:
            ctx.accounts.save(Account("Shark", "abc", "tok", "ct"))
        if pack:
            localpacks.save(home, LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", "Киберпанк", ""))
        if catalog is not None:
            monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda h: catalog)
        w = MainWindow(ctx, page_factory=FACTORY)
        w.show()
        pump(30)
        return w, w.page("home"), ctx
    yield build
    anim.set_enabled(True)


def test_login_shown_without_account_and_error_message(make):
    w, home, ctx = make(http=FakeHttp({f"{AUTH}/authenticate": err(401, "Invalid credentials.")}), account=False)
    assert home.mode() == "login"
    home.login.user.setText("shark")
    home.login.password.setText("wrong")
    home.login.submit()
    pump(until=lambda: home.login.error.text() != "")
    assert home.login.error.text() == "Неверный логин или пароль."


def test_login_2fa_field_appears(make):
    w, home, ctx = make(http=FakeHttp({f"{AUTH}/authenticate": err(401, "Account protected with two factor auth.")}),
                        account=False)
    assert not home.login.totp.isVisibleTo(home.login)
    home.login.user.setText("shark")
    home.login.password.setText("pw")
    home.login.submit()
    pump(until=lambda: home.login.totp.isVisibleTo(home.login))
    assert home.login.totp.isVisibleTo(home.login)


def test_login_success_shows_pack_and_account(make):
    ok = {"accessToken": "t", "clientToken": "c", "selectedProfile": {"id": "abc", "name": "Shark"}}
    w, home, ctx = make(http=FakeHttp({f"{AUTH}/authenticate": ok}), account=False)
    home.login.user.setText("shark")
    home.login.password.setText("pw")
    home.login.submit()
    pump(until=lambda: home.mode() == "pack")
    assert home.mode() == "pack" and w.rail.account_name == "Shark"
    assert ctx.accounts.load().name == "Shark"


def test_home_shows_pack_info_and_update_badge(make):
    cat = Catalog("0.1.0", {}, [PackEntry("net", ".NET", "Киберпанк", "0.2", "1.21.1", "neoforge", "21.1.267",
                                          "https://x/net-0.2.mrpack", "s", "Новые моды")])
    w, home, ctx = make(catalog=cat)
    pump(until=lambda: home.panel.update_box.isVisibleTo(home.panel))
    assert home.panel.title.text() == ".NET"
    assert home.panel.meta.text() == "Minecraft 1.21.1 с NeoForge, 0 модов"
    assert home.panel.update_box.isVisibleTo(home.panel) and "0.2" in home.panel.update_label.text()


def test_home_continue_world_newest(make, home):
    gd = home.instances / "net"
    for name, age in (("Старый", 100), ("Новый мир", 1)):
        (gd / "saves" / name).mkdir(parents=True)
        (gd / "saves" / name / "level.dat").write_bytes(b"x")
        os.utime(gd / "saves" / name / "level.dat", (time.time() - age, time.time() - age))
    w, page, ctx = make()
    assert page.panel.continue_btn.isVisibleTo(page.panel)
    assert page.panel.continue_btn.text() == "Продолжить «Новый мир»"


def test_play_needlogin_routes_to_login(make):
    http = FakeHttp({f"{AUTH}/validate": err(401, "expired"), f"{AUTH}/refresh": err(401, "gone")})
    w, home, ctx = make(http=http)
    assert home.mode() == "pack"
    home.play()
    pump(until=lambda: home.mode() == "login")
    assert home.mode() == "login" and ctx.accounts.load() is None


def _ready_game(monkeypatch, home_page):
    from netlauncher.gameinstall import InstalledGame
    monkeypatch.setattr(home_page.ctx.installer, "ensure", lambda *a, **k: InstalledGame("neoforge-21.1.267",
                                                                                          home_page.ctx.lay.root / "java"))
    monkeypatch.setattr(home_page.ctx.installer, "ensure_authlib", lambda: home_page.ctx.lay.root / "authlib.jar")
    monkeypatch.setattr("netlauncher.ui.pages.home.build_command", lambda spec: ["java", "-version"])
    procs = []

    def factory(gd):
        p = FakeProcess(gd)
        procs.append(p)
        return p
    home_page.process_factory = factory
    return procs


def test_play_follows_log_then_crash_card(make, monkeypatch, home):
    w, page, ctx = make()
    procs = _ready_game(monkeypatch, page)
    page.play()
    pump(until=lambda: bool(procs) and procs[0].cmd is not None)
    proc = procs[0]
    with open(proc.log_path, "a", encoding="utf-8") as f:
        f.write("[x] [main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args\n")
    pump(until=lambda: page.panel.status.text() == "Запуск")
    assert page.panel.status.text() == "Запуск"
    cr = home.instances / "net" / "crash-reports"
    cr.mkdir(parents=True)
    (cr / "crash-x-client.txt").write_text("Description: Rendering overlay\n\njava.lang.NullPointerException: boom\n",
                                           encoding="utf-8")
    proc.code = 1
    pump(until=lambda: page.panel.crash_box.isVisibleTo(page.panel))
    assert page.panel.crash_title.text() == "Игра закрылась с ошибкой"
    assert "Rendering overlay" in page.panel.crash_text.text()


def test_play_clean_exit_no_crash(make, monkeypatch):
    w, page, ctx = make()
    procs = _ready_game(monkeypatch, page)
    page.play()
    pump(until=lambda: bool(procs) and procs[0].cmd is not None)
    procs[0].code = 0
    pump(until=lambda: page.panel.play_btn.isEnabled())
    assert not page.panel.crash_box.isVisibleTo(page.panel) and page.panel.play_btn.isEnabled()


def test_empty_state_offers_catalog_and_import(make, monkeypatch, tmp_path):
    cat = Catalog("", {}, [PackEntry("net", ".NET", "Киберпанк", "0.1", "1.21.1", "neoforge", "21.1.267", "u", "s")])
    inst = tmp_path / "prism" / "1.21.1"
    inst.mkdir(parents=True)
    monkeypatch.setattr("netlauncher.ui.pages.home.find_instances", lambda: [inst])
    w, page, ctx = make(pack=False, catalog=cat)
    pump(until=lambda: page.empty.catalog_buttons)
    assert page.mode() == "empty"
    assert [b.text() for b in page.empty.catalog_buttons] == ["Установить"]
    assert [b.text() for b in page.empty.import_buttons] == ["Перенести «1.21.1»"]


def test_home_loads_skin_into_model_and_avatar(make):
    from netlauncher import skin
    from tests.test_skin import _two_tone_png
    png = _two_tone_png()
    http = FakeHttp({f"{AUTH}/validate": None,
                     skin.TEXTURES.format(name="Shark"): {"SKIN": {"url": "http://ely.by/s.png",
                                                                   "metadata": {"model": "slim"}}}},
                    downloads={"http://ely.by/s.png": png})
    w, page, ctx = make(http=http)
    pump(until=lambda: w.skin.skin_png == png)
    assert w.skin.skin_png == png and w.skin.slim
    assert w.rail.avatar.has_face()


def test_progress_bar_hidden_when_idle(make, monkeypatch):
    w, page, ctx = make()
    assert not page.panel.bar.isVisibleTo(page.panel)
    procs = _ready_game(monkeypatch, page)
    page.play()
    assert page.panel.bar.isVisibleTo(page.panel)
    pump(until=lambda: bool(procs) and procs[0].cmd is not None)
    procs[0].code = 0
    pump(until=lambda: page.panel.play_btn.isEnabled())
    assert not page.panel.bar.isVisibleTo(page.panel)


def test_skin_preview_from_file(make, tmp_path):
    from tests.test_skin import _two_tone_png
    w, page, ctx = make()
    png = _two_tone_png()
    f = tmp_path / "мой скин.png"
    f.write_bytes(png)
    assert not page.panel.skin_bar.isVisibleTo(page.panel)
    page.preview_skin(f)
    assert w.skin.skin_png == png and page.panel.skin_bar.isVisibleTo(page.panel)
    page.panel.slim.click()
    assert w.skin.slim
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"xx")
    page.preview_skin(bad)
    assert page.panel.skin_hint.text() == "Нужна картинка PNG размером 64×64 или 64×32."
    page.cancel_skin_preview()
    assert not page.panel.skin_bar.isVisibleTo(page.panel)


def test_first_run_has_no_theme_choice(qapp, home, monkeypatch):
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    ctx = make_context(home, FakeHttp())
    w = MainWindow(ctx, page_factory=FACTORY)
    w.show()
    page = w.page("home")
    assert page.mode() == "welcome"
    assert not hasattr(page.welcome, "cards")
    assert not hasattr(w, "theme") and not hasattr(w, "blurred") and not hasattr(w, "set_theme")
    page.welcome.done.emit()
    assert page.mode() == "login" and ctx.settings.first_run_done is True
    anim.set_enabled(True)


def test_update_snapshot_lands_in_pack_snapshots(make, home, monkeypatch, tmp_path):
    from netlauncher import pack as packmod
    seen = {}
    monkeypatch.setattr("netlauncher.ui.pages.home.apply_update",
                        lambda plan, pk, gd, http, cache, snaps, progress=None: seen.setdefault("snaps", snaps))
    monkeypatch.setattr("netlauncher.ui.pages.home.MrPack", type("P", (), {"open": staticmethod(
        lambda p: type("X", (), {"index": None})())}))
    monkeypatch.setattr("netlauncher.ui.pages.home.plan_update", lambda pk, gd, st: type("U", (), {"manual_missing": []})())
    w, page, ctx = make()
    monkeypatch.setattr(ctx.http, "download", lambda url, dest, sha1=None, sha512=None, progress=None: dest, raising=False)
    monkeypatch.setattr(ctx.installer, "ensure", lambda *a, **k: None)
    entry = PackEntry("net", ".NET", "", "0.2", "1.21.1", "neoforge", "21.1.267", "https://x/net.mrpack", "")
    page._install_job(entry, lambda *a: None)
    assert seen["snaps"] == ctx.lay.snapshots / "net"


def test_create_pack_flow(make, monkeypatch):
    from netlauncher import instances
    monkeypatch.setattr(instances, "minecraft_releases", lambda: ["26.3", "1.21.4", "1.21.1"])
    monkeypatch.setattr(instances, "loader_versions",
                        lambda loader, mc: {"fabric": ["0.16.9", "0.16.8"], "neoforge": ["21.4.10"]}.get(loader, []))
    w, page, ctx = make()
    called = {}
    monkeypatch.setattr(ctx.installer, "ensure",
                        lambda mc, loader, lv, progress, force=False: called.update(mc=mc, loader=loader, lv=lv))
    page.panel.new_btn.click()
    assert page.mode() == "create"
    c = page.creator
    pump(until=lambda: c.version.count() == 3)
    assert [c.version.itemText(i) for i in range(3)] == ["26.3", "1.21.4", "1.21.1"]
    c.name.setText("Тест Fabric")
    c.version.setCurrentIndex(1)
    c.pick_loader("fabric")
    pump(until=lambda: c.loader_version.count() == 2)
    assert c.loader_version.currentText() == "0.16.9"
    c.create_btn.click()
    pump(until=lambda: page.mode() == "pack" and page.panel.title.text() == "Тест Fabric")
    assert called == {"mc": "1.21.4", "loader": "fabric", "lv": "0.16.9"}
    assert ctx.settings.selected_pack == "test-fabric"
    assert page.panel.meta.text() == "Minecraft 1.21.4 с Fabric, 0 модов"


def test_create_vanilla_hides_loader_version(make, monkeypatch):
    from netlauncher import instances
    monkeypatch.setattr(instances, "minecraft_releases", lambda: ["1.21.1"])
    monkeypatch.setattr(instances, "loader_versions", lambda loader, mc: [])
    w, page, ctx = make()
    page.panel.new_btn.click()
    c = page.creator
    c.pick_loader("vanilla")
    assert not c.loader_line.isVisibleTo(c)
    c.pick_loader("forge")
    pump(until=lambda: c.hint.text().startswith("Для этой"))
    assert c.hint.text() == "Для этой версии Minecraft нет Forge. Выбери другую версию или загрузчик."
    assert not c.create_btn.isEnabled()


def test_empty_state_has_create(make, monkeypatch):
    monkeypatch.setattr("netlauncher.ui.pages.home.find_instances", lambda: [])
    w, page, ctx = make(pack=False)
    assert page.mode() == "empty" and page.empty.create_btn.text() == "Создать свою сборку"
    from netlauncher import instances
    monkeypatch.setattr(instances, "minecraft_releases", lambda: ["1.21.1"])
    page.empty.create_btn.click()
    assert page.mode() == "create"


def _own_pack(home):
    localpacks.save(home, LocalPack("mine", "Выживание с друзьями", "", "1.21.1", "fabric", "0.16.9"))


def test_scene_kind_by_pack(make):
    w, page, ctx = make()
    official = LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", official=True)
    own = LocalPack("mine", "Своя", "", "1.21.1", "fabric", "0.16.9")
    assert page.scene_kind(official) == "city"
    assert page.scene_kind(own) == "studio"
    assert page.scene_kind(None) == "plain"


def test_catalog_pack_counts_as_official(make):
    from netlauncher.catalog import Catalog, PackEntry
    cat = Catalog("0.2.2", {}, [PackEntry("net", ".NET", "", "0.1", "1.21.1", "neoforge", "21.1.267", "", "")])
    w, page, ctx = make(catalog=cat)
    pump(until=lambda: page.catalog is not None)
    assert page.scene_kind(localpacks.get(ctx.lay, "net")) == "city" and w.scene.kind == "city"


def test_switch_pack_dissolves(make, home):
    _own_pack(home)
    w, page, ctx = make()
    anim.set_enabled(True)
    page.pick_pack("mine")
    assert w.scene.transition_active()
    pump(1000)
    assert w.scene.kind == "studio" and not w.scene.transition_active()
    assert page.panel.title.text() == "Выживание с друзьями"


def test_play_hover_and_press_reactions(make, home, monkeypatch):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    _own_pack(home)
    w, page, ctx = make()
    page.pick_pack("mine")
    QApplication.sendEvent(page.panel.play_btn, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    assert w.skin.reaction == "ready"
    QApplication.sendEvent(page.panel.play_btn, QEvent(QEvent.Type.Leave))
    assert w.skin.reaction == "idle"
    monkeypatch.setattr(page, "play", lambda world=None, server=None: None)
    page.panel.play_btn.click()
    assert w.skin.reaction == "turn_head"


def test_display_font_is_oswald(qapp):
    from PySide6.QtGui import QFontDatabase
    from netlauncher.ui import theme as th
    assert th.DISPLAY == "Oswald" and "Oswald" in QFontDatabase.families()


def test_game_running_pauses_scene(make, monkeypatch):
    w, page, ctx = make()
    w.set_game_running(True)
    assert not w.scene.running()
    w.set_game_running(False)
    assert "game" not in w.scene._paused


def test_welcome_asks_shortcut_once(qapp, home, monkeypatch):
    from pathlib import Path
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    made = []
    monkeypatch.setattr("netlauncher.shortcut.create", lambda cmd, icon, name=".NET Launcher": made.append(cmd) or Path("/x"))
    ctx = make_context(home, FakeHttp())
    w = MainWindow(ctx, page_factory=FACTORY)
    w.show()
    page = w.page("home")
    assert page.welcome.shortcut.isChecked()
    page.welcome.next_btn.click()
    assert len(made) == 1 and ctx.settings.shortcut_asked is True
    page.welcome.done.emit()
    assert len(made) == 1
    anim.set_enabled(True)


def test_microsoft_login_button_in_development(make):
    w, page, ctx = make(account=False)
    btn = page.login.ms_button
    assert not btn.isEnabled() and btn.text() == "Войти через Microsoft"
    assert page.login.ms_note.text() == "В разработке"


def test_microsoft_login_english(make):
    from netlauncher import i18n
    from netlauncher.i18n_en import EN
    assert EN["Войти через Microsoft"] == "Sign in with Microsoft" and EN["В разработке"] == "In development"


def test_backup_before_official_update(make, home, monkeypatch):
    from netlauncher import localpacks as lpm
    from netlauncher import pack as packmod
    seen = {}

    def fake_apply(plan, pk, gd, http, cache, snaps, progress=None):
        seen["backups"] = sorted(p.name for p in (home.backups / "net").glob("*/*.zip"))
    monkeypatch.setattr("netlauncher.ui.pages.home.apply_update", fake_apply)
    monkeypatch.setattr("netlauncher.ui.pages.home.MrPack", type("P", (), {"open": staticmethod(
        lambda p: type("X", (), {"index": None})())}))
    monkeypatch.setattr("netlauncher.ui.pages.home.plan_update", lambda pk, gd, st: type("U", (), {"manual_missing": []})())
    monkeypatch.setattr("netlauncher.ui.pages.home.load_state", lambda gd: {"version": "0.1", "files": {}})
    w, page, ctx = make()
    gd = lpm.game_dir(ctx.lay, "net")
    (gd / "saves" / "Город").mkdir(parents=True)
    (gd / "saves" / "Город" / "level.dat").write_bytes(b"x")
    monkeypatch.setattr(ctx.http, "download", lambda url, dest, sha1=None, sha512=None, progress=None: dest, raising=False)
    monkeypatch.setattr(ctx.installer, "ensure", lambda *a, **k: None)
    entry = PackEntry("net", ".NET", "", "0.2", "1.21.1", "neoforge", "21.1.267", "https://x/net.mrpack", "")
    page._install_job(entry, lambda *a: None)
    assert len(seen["backups"]) == 1


def _official(home):
    localpacks.save(home, LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", "Киберпанк", "",
                                    official=True))


def test_play_runs_check_for_locked_pack_only(make, monkeypatch, home):
    from netlauncher import integrity
    checked = []
    monkeypatch.setattr(integrity, "check", lambda gd, st: checked.append(gd) or integrity.Report())
    w, page, ctx = make()
    procs = _ready_game(monkeypatch, page)
    page.play()
    pump(until=lambda: bool(procs) and procs[0].cmd is not None)
    assert checked == []
    procs[0].code = 0
    pump(until=lambda: page.panel.play_btn.isEnabled())
    _official(home)
    page.refresh()
    page.play()
    pump(until=lambda: len(procs) == 2 and procs[1].cmd is not None)
    assert checked == [home.instances / "net"]


def test_play_repairs_broken_official_pack(make, monkeypatch, home):
    from netlauncher import integrity
    repaired = []
    monkeypatch.setattr(integrity, "check", lambda gd, st: integrity.Report(extra=["mods/cheat.jar"]))
    monkeypatch.setattr(integrity, "repair",
                        lambda report, lay, lp, http, progress, mrpack_url="": repaired.append(report.extra) or integrity.Report())
    _official(home)
    w, page, ctx = make(pack=False)
    procs = _ready_game(monkeypatch, page)
    page.play()
    pump(until=lambda: bool(procs) and procs[0].cmd is not None)
    assert repaired == [["mods/cheat.jar"]]


def test_play_offline_with_broken_official_pack(make, monkeypatch, home):
    from netlauncher import integrity
    from netlauncher.net import Offline

    def offline_repair(*a, **k):
        raise Offline("x")
    monkeypatch.setattr(integrity, "check", lambda gd, st: integrity.Report(missing=["mods/a.jar"]))
    monkeypatch.setattr(integrity, "repair", offline_repair)
    _official(home)
    w, page, ctx = make(pack=False)
    procs = _ready_game(monkeypatch, page)
    page.play()
    pump(until=lambda: page.panel.play_btn.isEnabled() and page.panel.status.text() != "Проверяю вход и файлы игры")
    assert procs == []
    assert page.panel.status.text() == "Часть файлов сборки пропала или изменилась. Подключись к интернету, и лаунчер вернёт их."


def _cat(version="0.2", pack_id="net"):
    return Catalog("0.1.0", {}, [PackEntry(pack_id, ".NET", "Киберпанк", version, "1.21.1", "neoforge", "21.1.267",
                                           "https://x/net.mrpack", "s", "Новые моды")])


def test_play_becomes_update_when_newer(make, home):
    _official(home)
    w, page, ctx = make(pack=False, catalog=_cat("0.2"))
    pump(until=lambda: page.play_action() == "update")
    assert page.panel.play_btn.text() == "Обновить"
    assert not page.panel.update_btn.isVisibleTo(page.panel)
    assert not page.panel.continue_btn.isVisibleTo(page.panel) and not page.panel.server_btn.isVisibleTo(page.panel)
    assert "0.2" in page.panel.update_label.text()


def test_update_button_runs_update(make, home, monkeypatch):
    _official(home)
    w, page, ctx = make(pack=False, catalog=_cat("0.2"))
    pump(until=lambda: page.play_action() == "update")
    started = []
    monkeypatch.setattr(page, "install_entry", lambda entry: started.append(entry.version))
    page.panel.play_btn.click()
    assert started == ["0.2"]
    page.play()
    assert started == ["0.2", "0.2"]


def test_offline_keeps_play(make, home):
    _official(home)
    w, page, ctx = make(pack=False, catalog=None)
    pump(50)
    assert page.play_action() == "play" and page.panel.play_btn.text() == "Играть"


def test_same_version_keeps_play(make, home):
    _official(home)
    w, page, ctx = make(pack=False, catalog=_cat("0.1"))
    pump(50)
    assert page.play_action() == "play" and page.panel.play_btn.text() == "Играть"


def test_own_pack_never_update(make, home):
    localpacks.save(home, LocalPack("mine", "Своя", "", "1.21.1", "fabric", "0.16.9"))
    w, page, ctx = make(pack=False, catalog=_cat("0.2"))
    page.pick_pack("mine")
    pump(50)
    assert page.play_action() == "play" and page.panel.play_btn.text() == "Играть"


def test_guest_can_open_an_installed_pack(make, monkeypatch):
    w, page, ctx = make(account=False)
    monkeypatch.setattr("netlauncher.ui.pages.home.QInputDialog.getText", lambda *args: ("Local_42", True))
    page.login.guest_btn.click()
    assert ctx.accounts.load().offline and page.mode() == "pack"


def test_disconnected_player_keeps_ely_world_identity(make, monkeypatch):
    w, page, ctx = make(http=FakeHttp(offline=True))
    stored = ctx.accounts.load()
    _ready_game(monkeypatch, page)
    seen = []
    monkeypatch.setattr("netlauncher.ui.pages.home.build_command", lambda spec: seen.append(spec) or ["java"])
    page.play()
    pump(until=lambda: seen)
    assert seen and seen[0].authlib is None
    assert seen[0].account.uuid == stored.uuid and seen[0].account.access_token == "0"
    assert ctx.accounts.load() == stored and w.offline
