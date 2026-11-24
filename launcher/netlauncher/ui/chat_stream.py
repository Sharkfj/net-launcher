"""A reconnecting, authenticated WebSocket and unread tray notifications."""
from __future__ import annotations

import json

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWebSockets import QWebSocket

from netlauncher.i18n import t
from netlauncher.ui import icons


class ChatStream(QObject):
    event = Signal(dict)
    connected = Signal()

    def __init__(self, client, room="", parent=None):
        super().__init__(parent)
        self.client, self.room = client, room
        self.socket = QWebSocket(parent=self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.open)
        self.delay = 1000
        self.closed = False
        self.socket.connected.connect(self._connected)
        self.socket.textMessageReceived.connect(self._receive)
        self.socket.disconnected.connect(self._retry)
        self.socket.errorOccurred.connect(self._retry)

    def open(self):
        if self.closed or not self.client.token:
            return
        try:
            self.client._active_account()
        except Exception:
            self.stop()
            return
        url = QUrl(self.client.base + "/v1/chat/live")
        url.setScheme("wss" if url.scheme()=="https" else "ws")
        if self.room:
            params = QUrlQuery()
            params.addQueryItem("room",self.room)
            url.setQuery(params)
        req = QNetworkRequest(url)
        req.setRawHeader(b"Authorization",b"Bearer "+self.client.token.encode())
        self.socket.open(req)

    def _connected(self):
        self.delay = 1000
        self.timer.stop()
        self.connected.emit()

    def _receive(self, raw):
        try:
            event = json.loads(raw)
        except ValueError:
            return
        if isinstance(event,dict) and not self.closed:
            self.event.emit(event)

    def _retry(self, *args):
        if not self.closed and not self.timer.isActive():
            self.timer.start(self.delay)
            self.delay = min(30000,self.delay*2)

    def stop(self):
        self.closed = True
        self.timer.stop()
        self.socket.abort()
        self.deleteLater()


def tray_count(window, count):
    tray = getattr(window,"tray",None)
    if not tray:
        return
    icon = icons.tray_icon()
    if count:
        pix = icon.pixmap(64,64)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#225DB0"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(22,21,42,42)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(23 if count < 100 else 17)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(22,21,42,42,Qt.AlignmentFlag.AlignCenter,str(count) if count<100 else "99+")
        p.end()
        icon = QIcon(pix)
    tray.setIcon(icon)
    tray.setToolTip(t("Непрочитанных сообщений: {n}",n=count) if count else ".NET Launcher")
