"""Appearance of player names and developer badges."""
import math
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QWidget

from netlauncher.i18n import t
from netlauncher.ui import anim, theme

DEVELOPER_UUID = "55ec7d5c635e48198f447f72ccaf288d"
OPTIONS = {
    "font": {"display": "Узкий", "sans": "Обычный", "mono": "Моноширинный"},
    "color": {"default": "Системный", "ice": "Ледяной", "mint": "Мятный", "gold": "Золотой", "lilac": "Сиреневый"},
    "motion": {"still": "Без анимации", "shimmer": "Блик", "pulse": "Пульсация"},
    "frame": {"aurora": "Северное сияние", "ice": "Лёд", "gold": "Янтарь", "none": "Без рамки"},
}
DEFAULT = {field: next(iter(values)) for field, values in OPTIONS.items()}
COLORS = {"ice": "#94D7FF", "mint": "#8BE2C9", "gold": "#F3C782", "lilac": "#CEADFF"}


def clean(style):
    style = style if isinstance(style, dict) else {}
    return {field: value if isinstance(value := style.get(field), str) and value in choices else DEFAULT[field]
            for field, choices in OPTIONS.items()}


def is_developer(uuid):
    return isinstance(uuid, str) and uuid.replace("-", "").lower() == DEVELOPER_UUID


class DeveloperBadge(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)
        self.setToolTip(t("Разработчик"))
        self.setAccessibleName(self.toolTip())
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#A4C9FB"), 1.3, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QColor("#34557C"))
        path = QPainterPath(QPointF(4, 16))
        for x, y in [(3, 15), (10, 8), (8, 6), (6, 7), (6, 5), (9, 3),
                     (12, 4), (17, 9), (14, 12), (12, 10), (5, 17)]:
            path.lineTo(x, y)
        path.closeSubpath()
        painter.drawPath(path)


class PlayerName(QLabel):
    def __init__(self, size=18):
        super().__init__()
        self.points = size
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.update)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.set_appearance(None)

    def set_appearance(self, style):
        self.style = clean(style)
        family = {"display": theme.DISPLAY, "sans": theme.BODY,
                  "mono": QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()}[self.style["font"]]
        self.setFont(theme.font(self.points, 650, family))
        self.schedule()
        self.update()

    def schedule(self):
        moving = self.isVisible() and self.style["motion"] != "still" and anim.enabled()
        if moving and not self.timer.isActive():
            self.timer.start()
        elif not moving:
            self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.schedule()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        color = QColor(COLORS.get(self.style["color"], theme.TOKENS["text"]))
        motion = self.style["motion"] if anim.enabled() else "still"
        phase = (time.monotonic() % 3.2) / 3.2
        if motion == "shimmer":
            width = max(20, self.fontMetrics().horizontalAdvance(self.text()))
            x = phase*(width+48)-24
            gradient = QLinearGradient(x-24, 0, x+24, 0)
            gradient.setColorAt(0, color.darker(120))
            gradient.setColorAt(.5, QColor("#FFFFFF"))
            gradient.setColorAt(1, color.darker(120))
            painter.setPen(QPen(gradient, 1))
        else:
            if motion == "pulse":
                color.setAlphaF(.82 + .18 * math.cos(phase*2*math.pi))
            painter.setPen(color)
        painter.drawText(self.contentsRect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
