import json
import struct
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication

from netlauncher import discord_presence as rpc
from netlauncher.settings import Settings


def test_desktop_handshake_game_lifecycle_and_disable(monkeypatch):
    class Socket(QObject):
        LocalSocketState = QLocalSocket.LocalSocketState
        connected, readyRead, disconnected = Signal(), Signal(), Signal()

        def __init__(self, parent):
            super().__init__(parent)
            self.output = []
            self.incoming = b""
            self.live = False

        def state(self):
            return self.LocalSocketState.ConnectedState if self.live else self.LocalSocketState.UnconnectedState

        def connectToServer(self, name):
            self.live = True
            self.connected.emit()

        def write(self, data):
            op, size = struct.unpack_from("<II", data)
            assert len(data) == size+8
            self.output.append((op, json.loads(data[8:])))

        def readAll(self):
            data, self.incoming = self.incoming, b""
            return data

        def push(self, data):
            self.incoming = data
            self.readyRead.emit()

        def flush(self):
            pass

        def abort(self):
            self.live = False
            self.disconnected.emit()

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(rpc, "QLocalSocket", Socket)
    monkeypatch.setattr(rpc, "endpoints", lambda: ["discord-ipc-0"])
    ctx = SimpleNamespace(settings=Settings(),
                          current_window=SimpleNamespace(game_status=("launcher", "", "")))
    presence = rpc.DiscordPresence(ctx, app)
    sock = presence.socket
    try:
        assert sock.output == [(0, {"v": 1, "client_id": "1574673074132099092"})]
        ready = rpc.packet(1, {"evt": "READY"})
        sock.push(ready[:5])
        sock.push(ready[5:])
        assert sock.output[-1][1]["args"]["activity"]["details"] == "В лаунчере"
        ctx.current_window.game_status = ("playing", "Выживание", "private-server")
        presence.tick()
        game = sock.output[-1][1]["args"]["activity"]
        assert game["state"] == "Сборка: Выживание" and game["assets"]["large_image"].endswith("icon.png")
        assert "private-server" not in str(game)
        sock.push(rpc.packet(3, {"time": 1}))
        assert sock.output[-1] == (4, {"time": 1})
        ctx.current_window.game_status = ("launcher", "", "")
        presence.tick()
        assert "state" not in sock.output[-1][1]["args"]["activity"]
        ctx.settings.discord_presence = False
        presence.configure()
        assert sock.output[-1][1]["args"]["activity"] is None and not presence.timer.isActive()
    finally:
        presence.close()
