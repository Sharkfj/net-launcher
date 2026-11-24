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


def _friends(p: QPainterPath):
    p.addEllipse(QPointF(7.5, 7), 2.8, 2.8)
    p.moveTo(2.5, 16.5); p.cubicTo(2.5, 12.5, 12.5, 12.5, 12.5, 16.5)  # noqa: E702
    p.addEllipse(QPointF(13.8, 7.6), 2.3, 2.3)
    p.moveTo(13.5, 12.2); p.cubicTo(16, 12.2, 17.6, 13.6, 17.6, 16)  # noqa: E702


def _minimize(p: QPainterPath):
    p.moveTo(5.5, 10); p.lineTo(14.5, 10)  # noqa: E702


def _close(p: QPainterPath):
    p.moveTo(6, 6); p.lineTo(14, 14); p.moveTo(14, 6); p.lineTo(6, 14)  # noqa: E702


def _play(p: QPainterPath):
    p.moveTo(6.5, 4.5); p.lineTo(15.5, 10); p.lineTo(6.5, 15.5); p.closeSubpath()  # noqa: E702


def _packs(p: QPainterPath):  # four tiles
    for x, y in ((3, 3), (11.5, 3), (3, 11.5), (11.5, 11.5)):
        p.addRoundedRect(QRectF(x, y, 5.5, 5.5), 1.3, 1.3)


def _official(p: QPainterPath):  # a shield with a tick
    p.moveTo(10, 2.5); p.lineTo(16.5, 5.4); p.lineTo(16.5, 9.8)  # noqa: E702
    p.cubicTo(16.5, 13.8, 13.7, 16.4, 10, 17.5); p.cubicTo(6.3, 16.4, 3.5, 13.8, 3.5, 9.8)  # noqa: E702
    p.lineTo(3.5, 5.4); p.closeSubpath()  # noqa: E702
    p.moveTo(7, 10); p.lineTo(9.1, 12.1); p.lineTo(13, 8.2)  # noqa: E702


def _search(p: QPainterPath):
    p.addEllipse(QPointF(8.8, 8.8), 5, 5)
    p.moveTo(12.6, 12.6); p.lineTo(16.5, 16.5)  # noqa: E702


DRAW = {"home": _home, "mods": _mods, "resourcepacks": _resourcepacks, "shaders": _shaders,
        "snapshots": _snapshots, "settings": _settings, "friends": _friends, "minimize": _minimize, "close": _close,
        "play": _play, "search": _search, "packs": _packs, "official": _official}
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
    """Launcher tile used by the desktop and window manager."""
    from pathlib import Path
    png = Path(__file__).parent / "assets" / "icon" / "icon.png"
    icon = QIcon()
    src = QPixmap(str(png))
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(src.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    return icon


def tray_icon() -> QIcon:
    from netlauncher.ui.theme import ASSETS
    return QIcon(str(ASSETS / "icon" / "tray.png"))
