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
    assert home.mode() == "pack" and w.sidebar.account.text() == "Shark"
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
    pump(until=lambda: page.panel.model.skin_png == png)
    assert page.panel.model.skin_png == png and page.panel.model.slim
    assert w.sidebar.avatar.has_face()


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
