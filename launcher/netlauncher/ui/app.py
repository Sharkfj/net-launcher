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
CREDITS = ["@looper_fj", "Claude Code"]


@dataclass
class AppContext:
    lay: Layout
    settings: Settings
    http: Http
    modrinth: Modrinth
    auth: ElyAuth
    accounts: AccountStore
    installer: GameInstaller

    def save(self) -> None:
        save_settings(self.lay.settings_file, self.settings)


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
    from netlauncher.ui import theme
    from netlauncher.ui.window import MainWindow
    theme.apply(app)
    ctx = make_context(layout(), RequestsHttp())
    from netlauncher.ui import anim
    anim.set_enabled(ctx.settings.animations)
    win = MainWindow(ctx, page_factory=_pages())
    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.restore_from_tray()))
    win.show()
    return app.exec()


def _pages() -> dict:
    try:
        from netlauncher.ui.pages import FACTORY
    except ImportError:
        return {}
    return FACTORY
