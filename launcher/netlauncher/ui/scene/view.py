"""The widget under all pages: draws the current scene, moves the tab camera, dissolves between scenes."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRect, QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from netlauncher.ui import anim
from netlauncher.ui.scene.city import BAYER, CityScene
from netlauncher.ui.scene.springs import Springs
from netlauncher.ui.scene.studio import StudioScene

PLAIN = QColor("#0A101D")
BLOCK = 8
DISSOLVE_MS = 620


def dissolve_mask_widths(progress: float, cols: int) -> list[int]:
    """How many block columns are already cleared for each of the 16 Bayer classes."""
    out = []
    for b in BAYER:
        x = (progress - .55 * b) / .45 * cols
        out.append(max(0, math.ceil(x)))
    return out


def _class_brushes() -> list[QBrush]:
    brushes = []
    for i in range(16):
        bx, by = i % 4, i // 4
        img = QImage(4 * BLOCK, 4 * BLOCK, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.fillRect(QRect(bx * BLOCK, by * BLOCK, BLOCK, BLOCK), QColor(0, 0, 0, 255))
        p.end()
        brushes.append(QBrush(img))
    return brushes


class SceneView(QWidget):
    def __init__(self, parent: QWidget | None = None, radius: float = 0.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.radius = radius
        self.kind = "plain"
        self.tab = "home"
        self.shade = "home"
        self.city: CityScene | None = None
        self.studio = StudioScene()
        self.profile_studio = StudioScene()
        self.profile_studio.backdrop = "profile"
        self._paused: set[str] = set()
        self._trans: dict | None = None
        self._brushes: list[QBrush] | None = None
        self.parallax = QPointF(0, 0)
        self.cam = Springs({"x": 0.0, "y": 0.0, "z": 0.0}, default_k=7.0)
        self._last = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # ---------- api ----------
    def scene(self):
        if self.tab == "profile":
            return self.profile_studio
        if self.kind == "city":
            if self.city is None:
                self.city = CityScene()
            return self.city
        if self.kind == "studio":
            return self.studio
        return None

    def set_scene(self, kind: str, animate: bool = True, force: bool = False) -> None:
        """force: dissolve even when the scene kind stays the same (switching between two packs)."""
        if kind not in ("city", "studio", "plain"):
            raise ValueError(kind)
        if kind == self.kind and self._trans is None and not force:
            return
        if self.tab != "profile" and animate and anim.enabled() and self.isVisible() and self.width() > 0:
            self._trans = {"t0": time.monotonic(), "img": self.snapshot()}
        else:
            self._trans = None
        self.kind = kind
        self.scene()
        self._sync()
        self.update()

    def set_tab(self, name: str) -> None:
        if "profile" in (self.tab, name):
            self._trans = None
        self.tab = name
        x, y, z = CityScene.CAMERAS.get(name, CityScene.CAMERAS["home"])
        self.cam.set_targets({"x": x, "y": y, "z": z})
        if self.studio.skin is not None:
            self.studio.skin.set_tab(name)
        if not anim.enabled():
            self.cam.snap({"x": x, "y": y, "z": z})
        self._sync()
        self.update()

    def set_shade(self, mode: str) -> None:
        """Darkening under the page text: "home" (bottom-left, behind the title) or "deep" (behind lists)."""
        self.shade = mode
        self.update()

    def set_paused(self, reason: str, on: bool) -> None:
        if on:
            self._paused.add(reason)
        else:
            self._paused.discard(reason)
        self._sync()

    def running(self) -> bool:
        return self.timer.isActive()

    def transition_active(self) -> bool:
        return self._trans is not None

    def snapshot(self) -> QImage:
        img = QImage(max(1, self.width()), max(1, self.height()), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        self._paint_scene(p)
        p.end()
        return img

    # ---------- timing ----------
    def _camera_moving(self) -> bool:
        skin = self.studio.skin
        return self.cam.moving(5e-3) or (self.kind == "studio" and skin is not None and skin.moving())

    def _wanted(self) -> bool:
        """Animate on the home tab; elsewhere only until the camera has reached the tab's framing."""
        if not self.isVisible() or self._paused:
            return False
        if self._trans is not None:
            return True
        if not anim.enabled() or (self.kind == "plain" and self.tab != "profile"):
            return False
        return self.tab in ("home", "profile") or self._camera_moving()

    def _sync(self) -> None:
        if self._wanted():
            if not self.timer.isActive():
                self._last = time.monotonic()
                self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._sync()

    def hideEvent(self, e):  # noqa: N802
        self.timer.stop()
        super().hideEvent(e)

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        sc = self.scene()
        if sc is not None and anim.enabled():
            sc.step(dt)
        self.cam.step(dt)
        if self.width() > 0:
            g = self.mapFromGlobal(QCursor.pos())
            tx = max(-1.0, min(1.0, g.x() / self.width() * 2 - 1))
            ty = max(-1.0, min(1.0, g.y() / max(1, self.height()) * 2 - 1))
            k = min(1.0, dt * 8)
            self.parallax = QPointF(self.parallax.x() + (tx - self.parallax.x()) * k,
                                    self.parallax.y() + (ty - self.parallax.y()) * k)
            skin = self.profile_studio.skin if self.tab == "profile" else self.studio.skin
            if skin is not None:
                skin.look_at(tx, ty)
        dissolving = self._trans is not None
        if dissolving and (now - self._trans["t0"]) * 1000 >= DISSOLVE_MS:
            self._trans = None
        if isinstance(sc, StudioScene) and not dissolving:
            # Dust and the animated skin share the same strip on the right.
            self.update(sc.skin_rect(self.size()).toAlignedRect())
        else:
            self.update()
        if not self._wanted():
            self._sync()

    # ---------- painting ----------
    def _paint_scene(self, p: QPainter) -> None:
        size = self.size()
        sc = self.scene()
        if sc is None:
            p.fillRect(QRect(0, 0, size.width(), size.height()), PLAIN)
        elif sc is self.city:
            sc.render(p, size, self.parallax, (self.cam["x"], self.cam["y"], self.cam["z"]))
        else:
            sc.render(p, size, self.parallax, self.tab)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        if self.radius:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
            p.setClipPath(clip)
        self._paint_scene(p)
        if self._trans is not None:
            k = min(1.0, (time.monotonic() - self._trans["t0"]) * 1000 / DISSOLVE_MS)
            progress = k * k * (3 - 2 * k) * 1.35
            over = self._trans["img"].copy()
            q = QPainter(over)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            if self._brushes is None:
                self._brushes = _class_brushes()
            cols = math.ceil(over.width() / BLOCK)
            for brush, n in zip(self._brushes, dissolve_mask_widths(progress, cols)):
                if n > 0:
                    q.fillRect(QRect(0, 0, n * BLOCK, over.height()), brush)
            q.end()
            p.drawImage(0, 0, over)
        self._paint_shade(p)
        if self.radius:
            p.setClipping(False)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor(255, 255, 255, 26), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), self.radius, self.radius)

    def _paint_shade(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        if self.tab == "profile":
            return
        if self.shade == "deep":
            g = QLinearGradient(0, 0, w, 0)
            for at, a in ((0, .94), (.5, .88), (1, .78)):
                g.setColorAt(at, QColor(4, 7, 14, int(a * 255)))
        elif self.kind == "studio":
            g = QLinearGradient(0, 0, w, 0)
            g.setColorAt(0, QColor(4, 7, 14, 128))
            g.setColorAt(.48, QColor(4, 7, 14, 0))
        else:
            dx, dy = math.sin(math.radians(16)), -math.cos(math.radians(16))
            ln = abs(w * dx) + abs(h * dy)
            cx, cy = w / 2, h / 2
            g = QLinearGradient(cx - dx * ln / 2, cy - dy * ln / 2, cx + dx * ln / 2, cy + dy * ln / 2)
            for at, a in ((0, .93), (.38, .55), (.64, 0)):
                g.setColorAt(at, QColor(4, 7, 14, int(a * 255)))
        p.fillRect(QRectF(0, 0, w, h), g)
