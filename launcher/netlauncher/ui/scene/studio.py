"""Backdrop for a player's own pack: a dark stage, a beam of light and the player's skin."""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient

# The skin stands in this part of a 1180x720 window; other sizes scale it.
SKIN_RECT = (660, 0, 580, 720)


class StudioScene:
    def __init__(self, seed: int = 2):
        self.rng = random.Random(seed)
        self.skin = None  # SkinRenderer, set by the window
        self._bg: QImage | None = None
        self.backdrop = "studio"
        self.t = 0.0
        self.dust = [[self.rng.random(), self.rng.random(), .008 + self.rng.random() * .014,
                      .6 + self.rng.random() * 1.4, .08 + self.rng.random() * .22] for _ in range(34)]

    def set_style(self, backdrop, pose):
        if backdrop != self.backdrop:
            self.backdrop = backdrop
            self._bg = None
        if self.skin is not None:
            self.skin.set_style_pose(pose)

    def step(self, dt: float) -> None:
        dt = min(max(dt, 0.0), .25)
        self.t += dt
        for d in self.dust:
            d[1] -= d[2] * dt
            if d[1] < -.01:
                d[1] = 1.01
                d[0] = self.rng.random()
        if self.skin is not None:
            self.skin.step(dt)

    def _backdrop(self, size: QSize) -> QImage:
        if self._bg is not None and self._bg.size() == size:
            return self._bg
        w, h = size.width(), size.height()
        img = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#060a15"))
        g.setColorAt(1, QColor("#0b1224"))
        p.fillRect(img.rect(), g)
        sx, sy = w / 1180, h / 720
        if self.backdrop == "profile":
            p.scale(sx, sy)
            halo = QRadialGradient(945, 315, 355)
            halo.setColorAt(0, QColor(91, 122, 165, 66))
            halo.setColorAt(.55, QColor(54, 85, 135, 36))
            halo.setColorAt(1, QColor(54, 85, 135, 0))
            p.fillRect(QRectF(0, 0, 1180, 720), halo)
            p.translate(945, 644)
            p.scale(1, .2)
            floor = QRadialGradient(0, 0, 240)
            floor.setColorAt(0, QColor(119, 156, 210, 63))
            floor.setColorAt(1, QColor(72, 106, 168, 0))
            p.fillRect(QRectF(-240, -240, 480, 480), floor)
            p.end()
            self._bg = img
            return img
        if self.backdrop in ("aurora", "depot"):
            from netlauncher.ui.scene.supporter_backdrops import draw_backdrop
            draw_backdrop(p, size, self.backdrop)
            p.end()
            self._bg = img
            return img
        p.save()
        p.scale(sx, sy)
        amber = QRadialGradient(790, 206, 270)
        amber.setColorAt(0, QColor(183, 111, 76, 42))
        amber.setColorAt(.48, QColor(113, 74, 90, 25))
        amber.setColorAt(1, QColor(51, 43, 72, 0))
        p.fillRect(QRectF(500, 0, 590, 520), amber)
        p.restore()
        beam = QPainterPath()
        beam.moveTo(1010 * sx, -40 * sy)
        beam.lineTo(1110 * sx, -40 * sy)
        beam.lineTo(1150 * sx, h)
        beam.lineTo(760 * sx, h)
        beam.closeSubpath()
        bg = QLinearGradient(1060 * sx, 0, 940 * sx, h)
        bg.setColorAt(0, QColor(100, 148, 178, 32))
        bg.setColorAt(1, QColor(90, 130, 210, 6))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.fillPath(beam, bg)
        p.save()
        p.translate(950 * sx, 640 * sy)
        p.scale(1, .16)
        pool = QRadialGradient(0, 0, 240 * sx)
        pool.setColorAt(0, QColor(76, 130, 230, 56))
        pool.setColorAt(1, QColor(76, 130, 230, 0))
        p.fillRect(QRectF(-250 * sx, -240 * sx, 500 * sx, 480 * sx), pool)
        p.restore()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        vg = QRadialGradient(760 * sx, 340 * sy, 820 * sx, 760 * sx, 340 * sy, 200 * sx)
        vg.setColorAt(0, QColor(0, 0, 0, 0))
        vg.setColorAt(1, QColor(0, 0, 0, 150))
        p.fillRect(img.rect(), vg)
        p.end()
        self._bg = img
        return img

    def skin_rect(self, size: QSize) -> QRectF:
        sx, sy = size.width() / 1180, size.height() / 720
        x, y, w, h = SKIN_RECT
        return QRectF(x * sx, y * sy, w * sx, h * sy)

    def render(self, p: QPainter, size: QSize, parallax: QPointF, cam_tab: str) -> None:
        p.drawImage(0, 0, self._backdrop(size))
        w, h = size.width(), size.height()
        x0 = 860 / 1180 * w
        span = 240 / 1180 * w
        for x, y, _v, r, a in self.dust:
            p.setPen(QColor(0, 0, 0, 0))
            p.setBrush(QColor(170, 200, 255, int(a * 255)))
            p.drawEllipse(QPointF(x0 + x * span, y * h), r, r)
        if self.skin is not None:
            self.skin.paint(p, self.skin_rect(size))
