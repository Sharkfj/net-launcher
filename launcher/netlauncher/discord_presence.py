"""Publish launcher and pack activity to the local Discord desktop client."""
import json
import os
from pathlib import Path
import re
import struct
import sys
import time
import uuid

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalSocket

from netlauncher.i18n import t

APPLICATION_ID = "1574673074132099092"
LOGO = "https://raw.githubusercontent.com/Sharkfj/net-launcher/main/launcher/packaging/icon.png"


def endpoints():
    names = [f"discord-ipc-{n}" for n in range(10)]
    if sys.platform == "win32":
        return names
    roots = [Path(value) for key in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")
             if (value := os.environ.get(key))]
    roots += [Path("/tmp")]
    paths = (p / name for root in dict.fromkeys(roots)
             for p in (root, root / "app/com.discordapp.Discord", root / "snap.discord")
             for name in names)
    return [str(p) for p in paths if p.is_socket()]


def packet(op, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return struct.pack("<II", op, len(body)) + body


def activity(pack, since):
    result = {"type": 0, "details": t("Играет в Minecraft") if pack else t("В лаунчере"),
              "timestamps": {"start": since}, "assets": {"large_image": LOGO, "large_text": ".NET Launcher"}}
    if pack:
        result["state"] = t("Сборка: {name}", name=pack)[:128]
    return result


class DiscordPresence(QObject):
    def __init__(self, ctx, parent):
        super().__init__(parent)
        self.ctx = ctx
        self.socket = QLocalSocket(self)
        self.socket.connected.connect(self.handshake)
        self.socket.readyRead.connect(self.receive)
        self.socket.disconnected.connect(self.disconnected)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.tick)
        self.app_id = ""
        self.ready = False
        self.buffer = bytearray()
        self.candidates = []
        self.next_scan = 0
        self.connecting_since = 0
        self.since = int(time.time())
        self.pack = ""
        self.sent = None
        self.configure()

    def configure(self):
        settings = self.ctx.settings
        value = settings.discord_app_id.strip() or APPLICATION_ID
        value = value if settings.discord_presence and re.fullmatch(r"[1-9][0-9]{16,19}", value) else ""
        if value != self.app_id:
            self.close()
            self.app_id = value
            self.next_scan = 0
            self.candidates.clear()
        if value:
            self.timer.start()
            self.tick()

    def close(self):
        self.timer.stop()
        if self.ready:
            self.send_activity(None)
            self.socket.flush()
        self.socket.abort()
        self.disconnected()

    def disconnected(self):
        self.ready = False
        self.sent = None
        self.buffer.clear()

    def tick(self):
        window = self.ctx.current_window
        status, name, _ = getattr(window, "game_status", ("launcher", "", ""))
        pack = name if status == "playing" else ""
        if pack != self.pack:
            self.pack = pack
            self.since = int(time.time())
        if self.ready:
            data = activity(self.pack, self.since)
            if data != self.sent:
                self.send_activity(data)
                self.sent = data
            return
        now = time.monotonic()
        if self.socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            if now - self.connecting_since < 5:
                return
            self.socket.abort()
        if not self.candidates:
            if now < self.next_scan:
                return
            self.candidates = endpoints()
            self.next_scan = now + 15
        if self.candidates:
            self.connecting_since = now
            self.socket.connectToServer(self.candidates.pop(0))

    def handshake(self):
        self.socket.write(packet(0, {"v": 1, "client_id": self.app_id}))

    def send_activity(self, data):
        self.socket.write(packet(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": data},
                                     "nonce": uuid.uuid4().hex}))

    def receive(self):
        self.buffer.extend(bytes(self.socket.readAll()))
        while len(self.buffer) >= 8:
            op, size = struct.unpack_from("<II", self.buffer)
            if size > 1024 * 1024:
                self.socket.abort()
                return
            if len(self.buffer) < 8 + size:
                return
            body = self.buffer[8:8+size]
            del self.buffer[:8+size]
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError):
                self.socket.abort()
                return
            if op == 3:
                self.socket.write(packet(4, data))
            elif op == 2 or not isinstance(data, dict):
                self.socket.abort()
                return
            elif op == 1 and data.get("evt") == "READY":
                self.ready = True
                self.tick()
