import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
import time

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit

from netlauncher import i18n, localpacks
from netlauncher.auth_ely import Account
from netlauncher.friends import ELY_JOIN
from netlauncher.localpacks import LocalPack
from netlauncher.modrinth import API
from netlauncher.settings import Settings
from netlauncher.ui import anim, theme
from netlauncher.ui.app import make_context
from netlauncher.ui.pages import FACTORY
from netlauncher.ui.window import MainWindow
from tests.fakes import FakeHttp

CYR = re.compile(r"[А-Яа-яЁё]")
FB = "https://friends.example.net"


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
        if t.elapsed() >= ms and (until is None or until() or t.elapsed() > 3000):
            break


def cyrillic_texts(root):
    found = []
    for w in root.findChildren(QLabel) + root.findChildren(QAbstractButton):
        if w.isVisibleTo(root) and CYR.search(w.text() or ""):
            found.append(w.text())
        if w.isVisibleTo(root) and CYR.search(w.toolTip() or ""):
            found.append(w.toolTip())
    for w in root.findChildren(QLineEdit):
        if w.isVisibleTo(root) and CYR.search(w.placeholderText() or ""):
            found.append(w.placeholderText())
    for w in root.findChildren(QComboBox):
        for i in range(w.count()):
            if CYR.search(w.itemText(i)):
                found.append(w.itemText(i))
    return found


def test_default_language_is_english():
    assert Settings().language == "en"


def test_no_russian_left_in_english_mode(qapp, home, monkeypatch):
    i18n.set_language("en")
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    st = {"me": "Shark", "friends": [{"name": "Vasya", "online": True, "status": "playing", "pack": "Cyber",
                                     "server": "play.example.net", "last_seen": time.time()},
                                    {"name": "Oleg", "online": False, "status": "", "pack": "", "server": "",
                                     "last_seen": time.time() - 9000}],
          "incoming": ["Petya"], "outgoing": ["Masha"],
          "invites": [{"from": "Vasya", "pack": "Cyber", "server": "play.example.net", "created": 1}]}
    http = FakeHttp({f"{API}/version_files": {}, f"{API}/search": {"hits": []}, f"{API}/tag/category": [],
                     f"{FB}/v1/auth/challenge": {"server_id": "s"}, ELY_JOIN: None,
                     f"{FB}/v1/auth/verify": {"token": "x", "name": "Shark"}, f"{FB}/v1/presence": st,
                     f"{FB}/v1/state": st})
    ctx = make_context(home, http)
    ctx.settings.first_run_done = True
    ctx.settings.author_mode = True
    ctx.settings.friends_url = FB
    ctx.settings.language = "en"
    ctx.accounts.save(Account("Shark", "abc", "tok", "ct"))
    localpacks.save(home, LocalPack("cyber", "Cyber", "0.1", "1.21.1", "neoforge", "21.1.267", "A pack", "srv"))
    gd = home.instances / "cyber"
    (gd / "saves" / "World").mkdir(parents=True)
    (gd / "saves" / "World" / "level.dat").write_bytes(b"x")
    (gd / "mods").mkdir()
    w = MainWindow(ctx, page_factory=FACTORY)
    w.show()
    pump(100)
    problems = {}
    home_page = w.page("home")
    for mode in ("pack", "login", "empty", "install", "manual", "welcome"):
        home_page._set_mode(mode)
        if mode == "install":
            home_page.busy.start("Cyber")
        pump(30)
        problems[f"home/{mode}"] = cyrillic_texts(home_page)
    home_page.creator.open()
    home_page._set_mode("create")
    pump(30)
    problems["home/create"] = cyrillic_texts(home_page)
    for name in ("mods", "resourcepacks", "shaders", "snapshots", "settings", "friends"):
        w.open_page(name)
        pump(300)
        problems[name] = cyrillic_texts(w.page(name))
    mods = w.page("mods")
    mods.open_browser()
    pump(200)
    problems["mods/browser"] = cyrillic_texts(mods)
    problems["rail"] = cyrillic_texts(w.rail)
    problems = {k: v for k, v in problems.items() if v}
    assert problems == {}


def test_language_switch_rebuilds_window(qapp, home, monkeypatch):
    i18n.set_language("en")
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    ctx = make_context(home, FakeHttp())
    ctx.settings.first_run_done = True
    w = MainWindow(ctx, page_factory=FACTORY)
    w.show()
    assert w.nav_button("packs").title == "Packs"
    w.open_page("settings")
    new = w.page("settings").set_language("ru")
    assert i18n.language() == "ru" and ctx.settings.language == "ru"
    assert new.nav_button("packs").title == "Сборки" and new.current_page() == "settings"
    assert not w.isVisible()


def test_welcome_language_chips(qapp, home, monkeypatch):
    i18n.set_language("en")
    anim.set_enabled(False)
    monkeypatch.setattr("netlauncher.ui.pages.home.resolve_catalog", lambda http: None)
    ctx = make_context(home, FakeHttp())
    w = MainWindow(ctx, page_factory=FACTORY)
    w.show()
    page = w.page("home")
    assert page.mode() == "welcome" and page.welcome.title.text() == "Welcome"
    new = page.welcome.pick_language("ru")
    assert new.page("home").welcome.title.text() == "Добро пожаловать"
    assert new.page("home").mode() == "welcome"


def _russian_keys():
    import ast
    import glob
    cyr = re.compile("[А-Яа-яЁё]")
    keys, plurals = set(), set()
    for f in glob.glob("netlauncher/**/*.py", recursive=True):
        for node in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args:
                a = node.args[0] if node.func.id == "t" else node.args[1] if node.func.id == "plural" else None
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and cyr.search(a.value):
                    (keys if node.func.id == "t" else plurals).add(a.value)
    return keys, plurals


def test_every_russian_string_has_english():
    from netlauncher.i18n_en import EN, EN_PLURAL
    keys, plurals = _russian_keys()
    assert keys and plurals
    assert sorted(keys - EN.keys()) == []
    assert sorted(plurals - EN_PLURAL.keys()) == []
