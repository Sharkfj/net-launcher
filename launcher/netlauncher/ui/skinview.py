"""Interactive 3D player model drawn with QPainter (orthographic, painter's algorithm)."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF, QRadialGradient, QTransform
from PySide6.QtWidgets import QSizePolicy, QWidget

from netlauncher.skin import Box, Skin, faces, parts
from netlauncher.ui import anim

BASE_YAW = 28.0
BASE_PITCH = 9.0


def _png(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def default_skin() -> Skin:
    """Our own neutral default skin (not Mojang's): blue jacket, dark trousers."""
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    colors = {"head": QColor("#D9A47E"), "body": QColor("#2E62B8"), "arm_r": QColor("#2E62B8"),
              "arm_l": QColor("#2E62B8"), "leg_r": QColor("#1B2235"), "leg_l": QColor("#1B2235")}
    for name, box in parts(64, 64, slim=False).items():
        for face_name, _c, (u, v, w, h), _n in faces(box):
            p.fillRect(u, v, w, h, colors[name])
    p.fillRect(8, 0, 8, 8, QColor("#3A2A22"))      # hair on top
    p.fillRect(8, 8, 8, 2, QColor("#3A2A22"))      # fringe
    for x in (0, 16, 24):
        p.fillRect(x, 8, 8, 3, QColor("#3A2A22"))  # hair on sides/back
    p.fillRect(24, 8, 8, 8, QColor("#3A2A22"))
    p.fillRect(9, 12, 2, 1, QColor("#F4F7FC"))
    p.fillRect(13, 12, 2, 1, QColor("#F4F7FC"))
    p.fillRect(10, 12, 1, 1, QColor("#1D3F7A"))
    p.fillRect(13, 12, 1, 1, QColor("#1D3F7A"))
    p.fillRect(11, 14, 2, 1, QColor("#9C6B52"))
    p.fillRect(20, 20, 8, 1, QColor("#4C9AFF"))    # collar line in the launcher accent
    for u, v in ((44, 20), (36, 52)):
        p.fillRect(u, v + 10, 4, 2, QColor("#D9A47E"))  # hands
    for u, v in ((4, 20), (20, 52)):
        p.fillRect(u, v + 10, 4, 2, QColor("#5E6B82"))  # shoes
    p.end()
    return Skin(_png(img), False)


def face(png: bytes) -> QImage:
    src = QImage.fromData(png).convertToFormat(QImage.Format.Format_ARGB32)
    out = src.copy(8, 8, 8, 8)
    if src.width() >= 48:
        p = QPainter(out)
        p.drawImage(0, 0, src.copy(40, 8, 8, 8))
        p.end()
    return out


def _rot_x(p, a):
    c, s = math.cos(a), math.sin(a)
    x, y, z = p
    return x, y * c - z * s, y * s + z * c


def _rot_y(p, a):
    c, s = math.cos(a), math.sin(a)
    x, y, z = p
    return x * c + z * s, y, -x * s + z * c


class SkinView3D(QWidget):
    def __init__(self, parent=None, animate: bool = True):
        super().__init__(parent)
        self.setMinimumSize(220, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.animate = animate
        self.yaw, self.pitch = BASE_YAW, BASE_PITCH
        self._sway = animate
        self._vel = 0.0
        self._drag = None
        self._t0 = time.monotonic()
        self._swing = 0.0
        self._img: QImage | None = None
        self._parts: dict[str, Box] = {}
        self._entered = False
        self.set_skin(default_skin(), entrance=False)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # ---------- api ----------
    def set_skin(self, sk: Skin | None, entrance: bool = True) -> None:
        sk = sk or default_skin()
        img = QImage.fromData(sk.png)
        if img.isNull() or img.width() != 64 or img.height() not in (32, 64):
            sk = default_skin()
            img = QImage.fromData(sk.png)
        self._img = img.convertToFormat(QImage.Format.Format_ARGB32)
        self._tiles = {}
        self.skin_png, self.slim = sk.png, sk.slim
        self._parts = parts(64, self._img.height(), sk.slim)
        if entrance and self.animate and not self._entered and anim.enabled():
            self._entered = True
            anim.tween(200.0, BASE_YAW, 1100, self._set_yaw)
        self.update()

    def _set_yaw(self, v):
        self.yaw = float(v)
        self.update()

    def set_pose(self, yaw: float, pitch: float) -> None:
        self._sway = False
        self.yaw, self.pitch = yaw, pitch
        self.update()

    def visible_faces(self) -> list[tuple[str, str]]:
        return [(name, fname) for name, fname, *_ in self._projected(layers=("base",))]

    # ---------- animation ----------
    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if self.animate and anim.enabled():
            self.timer.start()

    def hideEvent(self, e):  # noqa: N802
        self.timer.stop()
        super().hideEvent(e)

    def _tick(self):
        t = time.monotonic() - self._t0
        self._swing = math.sin(t * 1.25)
        if self._drag is None:
            if abs(self._vel) > 0.05:
                self.yaw += self._vel
                self._vel *= 0.92
            elif self._sway:
                self.yaw += (BASE_YAW + 9 * math.sin(t * 0.32) - self.yaw) * 0.02
        self.update()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.position()
            self._vel = 0.0
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag is not None:
            d = e.position() - self._drag
            self._drag = e.position()
            self.yaw += d.x() * 0.6
            self._vel = d.x() * 0.6
            self.pitch = max(-25.0, min(25.0, self.pitch + d.y() * 0.3))
            self.update()

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ---------- geometry ----------
    def _limb_angle(self, name: str) -> float:
        a = math.radians(6) * self._swing
        return {"arm_r": a, "arm_l": -a, "leg_r": -a * 0.45, "leg_l": a * 0.45}.get(name, 0.0)

    def _projected(self, layers=("base", "overlay")):
        w, h = self.width(), self.height()
        scale = min(h * 0.80 / 34.0, w * 0.80 / 20.0)
        cx, cy = w / 2, h * 0.47
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        out = []
        for name, base in self._parts.items():
            boxes = [("base", base)]
            if base.overlay is not None:
                boxes.append(("overlay", base.overlay))
            limb = self._limb_angle(name)
            for layer, box in boxes:
                if layer not in layers:
                    continue
                for fname, corners, uv, normal in faces(box):
                    def tf(p, is_normal=False):
                        if limb and box.pivot:
                            if is_normal:
                                p = _rot_x(p, limb)
                            else:
                                px, py, pz = box.pivot
                                q = _rot_x((p[0] - px, p[1] - py, p[2] - pz), limb)
                                p = (q[0] + px, q[1] + py, q[2] + pz)
                        if not is_normal:
                            p = (p[0], p[1] - 16.0, p[2])
                        return _rot_x(_rot_y(p, yaw), pitch)
                    n = tf(normal, True)
                    if n[2] <= 1e-6:
                        continue
                    pts = [tf(c) for c in corners]
                    depth = sum(p[2] for p in pts) / 4 + (0.01 if layer == "overlay" else 0)
                    screen = [QPointF(cx + p[0] * scale, cy - p[1] * scale) for p in pts]
                    out.append((name, fname, layer, depth, screen, uv, n))
        out.sort(key=lambda f: f[3])
        return out

    # ---------- painting ----------
    def _tile(self, u: int, v: int, w: int, h: int, shade: float) -> QImage:
        key = (u, v, w, h, round(shade, 2))
        cache = self.__dict__.setdefault("_tiles", {})
        if key not in cache:
            img = self._img.copy(u, v, w, h)
            if key[4] < 0.995:
                q = QPainter(img)
                q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                q.fillRect(0, 0, w, h, QColor(6, 10, 20, round(255 * (1 - key[4]))))
                q.end()
            cache[key] = img
        return cache[key]

    def paintEvent(self, e):  # noqa: N802
        if self._img is None:
            return
        p = QPainter(self)
        w, h = self.width(), self.height()
        scale = min(h * 0.80 / 34.0, w * 0.80 / 20.0)
        feet = QPointF(w / 2, h * 0.47 + 16 * scale * math.cos(math.radians(self.pitch)))
        g = QRadialGradient(feet, 11 * scale)
        g.setColorAt(0, QColor(0, 0, 0, 110))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(feet, 11 * scale, 3.2 * scale)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        for name, fname, layer, depth, screen, (u, v, tw, th), n in self._projected():
            if tw <= 0 or th <= 0:
                continue
            center = QPointF(sum(q.x() for q in screen) / 4, sum(q.y() for q in screen) / 4)
            grown = []
            for q in screen:
                d = q - center
                ln = math.hypot(d.x(), d.y()) or 1.0
                grown.append(q + d * (0.6 / ln))
            src = QPolygonF([QPointF(0, 0), QPointF(tw, 0), QPointF(tw, th), QPointF(0, th)])
            t = QTransform()
            if not QTransform.quadToQuad(src, QPolygonF(grown), t):
                continue
            shade = 0.72 + 0.28 * max(0.0, min(1.0, 0.35 + 0.65 * n[2] + 0.25 * n[1]))
            p.setTransform(t)
            p.drawImage(QRectF(0, 0, tw, th), self._tile(u, v, tw, th, shade))
            p.resetTransform()
