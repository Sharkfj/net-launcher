"""Line icons drawn with QPainter (no image files, crisp at any scale)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _home(p: QPainterPath):
    p.moveTo(3, 9.5); p.lineTo(10, 3.5); p.lineTo(17, 9.5)  # noqa: E702
    p.moveTo(5, 8); p.lineTo(5, 16.5); p.lineTo(15, 16.5); p.lineTo(15, 8)  # noqa: E702
    p.moveTo(8.5, 16.5); p.lineTo(8.5, 12); p.lineTo(11.5, 12); p.lineTo(11.5, 16.5)  # noqa: E702


def _mods(p: QPainterPath):  # an isometric block
    p.moveTo(10, 2.5); p.lineTo(16.5, 6); p.lineTo(16.5, 13.5); p.lineTo(10, 17.5)  # noqa: E702
    p.lineTo(3.5, 13.5); p.lineTo(3.5, 6); p.closeSubpath()  # noqa: E702
    p.moveTo(3.5, 6); p.lineTo(10, 9.8); p.lineTo(16.5, 6)  # noqa: E702
    p.moveTo(10, 9.8); p.lineTo(10, 17.5)  # noqa: E702


def _resourcepacks(p: QPainterPath):
    p.addRoundedRect(QRectF(3, 4, 14, 12), 2.5, 2.5)
    p.moveTo(3.5, 13.5); p.lineTo(8, 9); p.lineTo(11.5, 12.5); p.lineTo(13.5, 10.5); p.lineTo(16.5, 13.5)  # noqa: E702
    p.addEllipse(QPointF(13, 7.3), 1.2, 1.2)


def _shaders(p: QPainterPath):
    p.addEllipse(QPointF(10, 10), 3.4, 3.4)
    for i in range(8):
        a = i * math.pi / 4
        p.moveTo(10 + 5.4 * math.cos(a), 10 + 5.4 * math.sin(a))
        p.lineTo(10 + 7.2 * math.cos(a), 10 + 7.2 * math.sin(a))


def _snapshots(p: QPainterPath):
    p.arcMoveTo(QRectF(3, 3, 14, 14), 160)
    p.arcTo(QRectF(3, 3, 14, 14), 160, -320)
    p.moveTo(3.2, 7.2); p.lineTo(3.6, 10.6); p.lineTo(6.8, 9.6)  # noqa: E702
    p.moveTo(10, 6.5); p.lineTo(10, 10.3); p.lineTo(12.6, 11.8)  # noqa: E702


def _settings(p: QPainterPath):
    for y, x in ((5.5, 12.5), (10, 6.5), (14.5, 11)):
        p.moveTo(3, y); p.lineTo(17, y)  # noqa: E702
        p.addEllipse(QPointF(x, y), 1.8, 1.8)


def _minimize(p: QPainterPath):
    p.moveTo(5.5, 10); p.lineTo(14.5, 10)  # noqa: E702


def _close(p: QPainterPath):
    p.moveTo(6, 6); p.lineTo(14, 14); p.moveTo(14, 6); p.lineTo(6, 14)  # noqa: E702


def _play(p: QPainterPath):
    p.moveTo(6.5, 4.5); p.lineTo(15.5, 10); p.lineTo(6.5, 15.5); p.closeSubpath()  # noqa: E702


def _search(p: QPainterPath):
    p.addEllipse(QPointF(8.8, 8.8), 5, 5)
    p.moveTo(12.6, 12.6); p.lineTo(16.5, 16.5)  # noqa: E702


DRAW = {"home": _home, "mods": _mods, "resourcepacks": _resourcepacks, "shaders": _shaders,
        "snapshots": _snapshots, "settings": _settings, "minimize": _minimize, "close": _close,
        "play": _play, "search": _search}
FILLED = {"play"}


def path(name: str) -> QPainterPath:
    p = QPainterPath()
    DRAW[name](p)
    return p


def paint(painter: QPainter, name: str, rect: QRectF, color: QColor, width: float = 1.6) -> None:
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 20.0, rect.height() / 20.0)
    pen = QPen(color, width * 20.0 / max(rect.width(), 1.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(color if name in FILLED else Qt.BrushStyle.NoBrush)
    painter.drawPath(path(name))
    painter.restore()


def app_icon(size: int = 256) -> QIcon:
    """Blue rounded square with a geometric '.N' mark."""
    icon = QIcon()
    for s in (16, 32, 48, 64, 128, size):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0C1220"))
        p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.24, s * 0.24)
        p.setBrush(QColor("#4C9AFF"))
        u = s / 16.0
        p.drawEllipse(QRectF(3 * u, 10.2 * u, 2.2 * u, 2.2 * u))
        n = QPainterPath()
        n.moveTo(6.8 * u, 12.4 * u); n.lineTo(6.8 * u, 3.6 * u); n.lineTo(9.0 * u, 3.6 * u)  # noqa: E702
        n.lineTo(11.0 * u, 8.6 * u); n.lineTo(11.0 * u, 3.6 * u); n.lineTo(13.2 * u, 3.6 * u)  # noqa: E702
        n.lineTo(13.2 * u, 12.4 * u); n.lineTo(11.0 * u, 12.4 * u); n.lineTo(9.0 * u, 7.4 * u)  # noqa: E702
        n.lineTo(9.0 * u, 12.4 * u); n.closeSubpath()  # noqa: E702
        p.drawPath(n)
        p.end()
        icon.addPixmap(pm)
    return icon
