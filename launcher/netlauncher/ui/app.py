"""Application entry point and shared context."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from netlauncher import __version__
from netlauncher.auth_ely import AccountStore, ElyAuth
from netlauncher.gameinstall import GameInstaller
from netlauncher.modrinth import Modrinth
from netlauncher.net import Http, RequestsHttp
from netlauncher.paths import Layout, layout
from netlauncher.settings import Settings, load_settings, save_settings

SERVER_NAME = "net-launcher"
CREDITS = ["@looper_fj"]


@dataclass
class AppContext:
    lay: Layout
    settings: Settings
    http: Http
    modrinth: Modrinth
    auth: ElyAuth
    accounts: AccountStore
    installer: GameInstaller
    catalog: object = None
    current_window: object = None
    discord: object = None

    def save(self) -> None:
        save_settings(self.lay.settings_file, self.settings)

    def friends_url(self) -> str:
        return self.settings.friends_url or (getattr(self.catalog, "friends_url", "") if self.catalog else "")

    def friends(self):
        from netlauncher.friends import FriendsClient
        return FriendsClient(self.http, self.friends_url(), self.lay.root / "friends-session.json",
                             self.accounts.load)


def make_context(lay: Layout, http: Http) -> AppContext:
    return AppContext(lay, load_settings(lay.settings_file), http, Modrinth(http), ElyAuth(http),
                      AccountStore(lay.accounts_file), GameInstaller(lay, http))


def _already_running() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("NET Launcher")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("net-launcher")
    if _already_running():
        return 0
    from netlauncher import i18n
    lay = layout()
    i18n.set_language(load_settings(lay.settings_file).language)
    from netlauncher.ui import theme
    from netlauncher.ui.window import MainWindow
    theme.apply(app)
    theme.follow_local_design(app, lay.root)
    ctx = make_context(lay, RequestsHttp())
    from netlauncher.ui import anim
    anim.set_enabled(ctx.settings.animations)
    win = MainWindow(ctx, page_factory=_pages())
    from netlauncher.discord_presence import DiscordPresence
    ctx.discord = DiscordPresence(ctx, app)
    app.aboutToQuit.connect(ctx.discord.close)
    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), ctx.current_window.restore_from_tray()))
    win.show()
    if anim.enabled():
        from netlauncher.ui.splash import Splash
        home = win.page("home")
        Splash(win, lambda: getattr(home, "startup_done", True)).start()
    return app.exec()


def _pages() -> dict:
    try:
        from netlauncher.ui.pages import FACTORY
    except ImportError:
        return {}
    return FACTORY
