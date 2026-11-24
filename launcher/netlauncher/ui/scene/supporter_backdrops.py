"""Pixel-art backdrops for personal packs, drawn once per window size."""
import math
import random

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPen, QPolygonF


def draw_backdrop(p, size, name):
    rng = random.Random(93)
    p.save()
    p.scale(size.width() / 295, size.height() / 180)
    p.setRenderHint(p.RenderHint.Antialiasing, False)
    if name == "aurora":
        sky = QLinearGradient(0, 0, 0, 180)
        sky.setColorAt(0, QColor("#080e27"))
        sky.setColorAt(.58, QColor("#173648"))
        sky.setColorAt(1, QColor("#10162a"))
        p.fillRect(QRectF(0, 0, 295, 180), sky)
        for _ in range(80):
            p.fillRect(rng.randrange(295), rng.randrange(92), 1, 1, QColor(175, 213, 225, rng.randrange(50, 170)))
        for x in range(295):
            y = 35 + 13 * math.sin(x / 34) + 9 * math.sin(x / 21)
            height = 11 + 9 * (1 + math.cos(x / 42))
            ribbon = QLinearGradient(0, y - height, 0, y + 3)
            ribbon.setColorAt(0, QColor(106, 104, 206, 0))
            ribbon.setColorAt(.78, QColor(104, 230, 190, 48 + rng.randrange(28)))
            ribbon.setColorAt(1, QColor(84, 225, 202, 0))
            p.fillRect(QRectF(x, y-height, 1, height+3), ribbon)
        for horizon, color, spacing in [(107, "#192e41", 9), (126, "#122333", 7), (147, "#0d1729", 5)]:
            p.setPen(QColor(color))
            p.setBrush(QColor(color))
            peaks = [QPointF(x, horizon - rng.randrange(14)) for x in range(-5, 308, spacing)]
            p.drawPolygon(QPolygonF(peaks + [QPointF(305, 180), QPointF(-5, 180)]))
    else:
        wall = QLinearGradient(0, 0, 0, 180)
        wall.setColorAt(0, QColor("#30212e"))
        wall.setColorAt(.68, QColor("#503c39"))
        wall.setColorAt(1, QColor("#201f2c"))
        p.fillRect(QRectF(0, 0, 295, 180), wall)
        for x in range(-6, 295, 36):
            p.fillRect(x, 0, 3, 131, QColor("#25202a"))
            p.fillRect(x+4, 36, 26, 39, QColor("#241f2a"))
            for i in range(3):
                for j in range(3):
                    p.fillRect(x+6+i*8, 38+j*12, 7, 10, QColor(rng.choice(["#895645", "#68484a", "#705052"])))
            p.fillRect(x+9, 21, 15, 1, QColor("#eda96c"))
        p.fillRect(0, 131, 295, 49, QColor("#24222c"))
        for x in range(-170, 530, 44):
            p.setPen(QPen(QColor("#44363b"), 1))
            p.drawLine(QPointF(203 + (x-203)*.09, 131), QPointF(x, 180))
        for y in (134, 138, 144, 154, 169):
            p.fillRect(0, y, 295, 1, QColor("#3f333b"))
    p.restore()
