"""Launch splash: the icon animation loops while the launcher loads, then '.NET' slides out from under it,
'Launcher' slides out of '.NET', and the icon flies to the top of the rail."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from netlauncher.ui import anim
from netlauncher.ui.theme import BODY, DISPLAY, font

ICON_DIR = Path(__file__).parent / "assets" / "icon"
FRAMES = len(list(ICON_DIR.glob("frame_*.png"))) or 1
FPS = 30
ICON = 240
GAP = 16


class BrandText(QWidget):
    """A word that can be revealed downward or sideways and scaled smoothly."""

    def __init__(self, text: str, f: QFont, color: str, axis: str, parent=None):
        super().__init__(parent)
        self.text, self.base, self.color, self.axis = text, f, QColor(color), axis
        self.fm = QFontMetricsF(f)
        self.scale = 1.0
        self.reveal = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._fit()

    def _fit(self) -> None:
        self.resize(round(self.fm.horizontalAdvance(self.text) * self.scale), round(self.fm.height() * self.scale))

    def text_width(self) -> float:
        return self.fm.horizontalAdvance(self.text) * self.scale

    def text_height(self) -> float:
        return self.fm.height() * self.scale

    def ascent(self) -> float:
        return self.fm.ascent() * self.scale

    def set_scale(self, s: float) -> None:
        self.scale = s
        self._fit()
        self.update()

    def set_reveal(self, v: float) -> None:
        self.reveal = max(0.0, min(1.0, float(v)))
        self.update()

    def paintEvent(self, e):  # noqa: N802
        if self.reveal <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        if self.axis == "down":
            p.setClipRect(QRectF(0, 0, w, h * self.reveal))
            p.translate(0, -(1 - self.reveal) * h * .6)
        else:
            p.setClipRect(QRectF(0, 0, w * self.reveal, h))
            p.translate(-(1 - self.reveal) * w * .4, 0)
        p.scale(self.scale, self.scale)
        p.setFont(self.base)
        p.setPen(self.color)
        p.drawText(QPointF(0, self.fm.ascent()), self.text)


class Splash(QWidget):
    finished = Signal()

    def __init__(self, window, ready: Callable[[], bool], speed: float = 1.0):
        super().__init__(window)
        self.window, self.ready, self.speed = window, ready, max(.1, speed)
        self.setGeometry(window.rect())
        self.phase = "idle"
        self.bg = 1.0
        self._frames = [QPixmap(str(ICON_DIR / f"frame_{i:02d}.png")) for i in range(FRAMES)]
        self.frame = 0.0
        self.icon = QLabel(self)
        self.icon.setScaledContents(True)
        self.icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.icon.setGeometry(self._icon_home())
        f = font(40, 600, DISPLAY)
        f.setPixelSize(110)
        self.net = BrandText(".NET", f, "#e8eefb", "down", self)
        g = font(20, 500, BODY)
        g.setPixelSize(32)
        self.lw = BrandText("Launcher", g, "#b8c6e0", "right", self)
        self.timer = QTimer(self)
        self.timer.setInterval(1000 // FPS)
        self.timer.timeout.connect(self._tick)
        self._t0 = self._last = 0.0
        self._timers: list[QTimer] = []

    # ---------- helpers ----------
    def _ms(self, ms: float) -> int:
        return max(1, round(ms / self.speed))

    def _later(self, ms: float, fn) -> None:
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(fn)
        t.start(self._ms(ms))
        self._timers.append(t)

    def _icon_home(self) -> QRect:
        w, h = self.width(), self.height()
        return QRect((w - ICON) // 2, (h - ICON) // 2 - 60, ICON, ICON)

    def _show_frame(self) -> None:
        self.icon.setPixmap(self._frames[int(self.frame) % FRAMES])

    def _rail_icon(self):
        return self.window.rail.icon_slot.findChild(QLabel, "rail_icon")

    # ---------- run ----------
    def start(self) -> None:
        self.raise_()
        self.show()
        ri = self._rail_icon()
        if ri is not None:
            ri.hide()
        self.phase = "loading"
        self._t0 = self._last = time.monotonic()
        self._show_frame()
        self.timer.start()

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = (now - self._last) * self.speed, now
        elapsed = (now - self._t0) * self.speed
        if self.phase == "loading":
            self.frame += FPS * dt
            if (elapsed >= 1.2 and self.ready()) or elapsed >= 8:
                self.phase = "settle"
        elif self.phase == "settle":
            left = (FRAMES - self.frame % FRAMES) % FRAMES
            step = FPS * dt * max(.15, min(1.0, left / 12))
            if left <= step or left < .5:
                self.frame = round(self.frame / FRAMES) * FRAMES
                self._show_frame()
                self.timer.stop()
                self._brand()
                return
            self.frame += step
        self._show_frame()

    def _brand(self) -> None:
        self.phase = "brand"
        home = self._icon_home()
        up = QRect(home.x(), home.y() - 50, ICON, ICON)
        anim.tween(QRect(home), up, self._ms(620), self.icon.setGeometry)
        nx = (self.width() - self.net.text_width()) / 2
        ny = home.bottom() - 14
        self.net.move(round(nx), round(ny))
        self.net.show()
        anim.tween(0.0, 1.0, self._ms(620), self.net.set_reveal)
        anim.tween(float(ny), float(ny - 50), self._ms(620), lambda v: self.net.move(self.net.x(), round(v)))
        self._later(750, self._launcher)

    def _launcher(self) -> None:
        total = self.net.text_width() + GAP + self.lw.text_width()
        nx2 = (self.width() - total) / 2
        anim.tween(float(self.net.x()), nx2, self._ms(520), lambda v: self.net.move(round(v), self.net.y()),
                   easing=QEasingCurve.Type.InOutCubic)
        base = self.net.y() + self.net.ascent()
        lx, ly = nx2 + self.net.text_width() + GAP, base - self.lw.ascent()
        self.lw.move(round(lx), round(ly))
        self.lw.show()
        anim.tween(0.0, 1.0, self._ms(560), self.lw.set_reveal)
        self._later(600, self._hold)

    def _hold(self) -> None:
        self.phase = "hold"
        self._later(600, self._fly)

    def _official_first(self) -> bool:
        home = self.window.page("home")
        return getattr(home, "mode", lambda: "")() == "pack" and self.window.scene.kind == "city"

    def _fly(self) -> None:
        self.phase = "fly"
        slot = self.window.rail.icon_slot
        o = slot.mapTo(self.window, QPoint(0, 0))
        anim.tween(QRect(self.icon.geometry()), QRect(o.x(), o.y(), slot.width(), slot.height()), self._ms(780),
                   self.icon.setGeometry, easing=QEasingCurve.Type.InOutCubic)
        anim.tween(1.0, 0.0, self._ms(320), self.lw.set_reveal)
        if self._official_first():
            title = self.window.page("home").panel.title
            to = title.mapTo(self.window, title.contentsRect().topLeft())
            s0, s1 = self.net.scale, QFontMetricsF(title.font()).height() / self.net.fm.height()
            x0, y0 = float(self.net.x()), float(self.net.y())

            def step(k):
                self.net.set_scale(s0 + (s1 - s0) * k)
                self.net.move(round(x0 + (to.x() - x0) * k), round(y0 + (to.y() - y0) * k))
            anim.tween(0.0, 1.0, self._ms(820), step, easing=QEasingCurve.Type.InOutCubic)
        else:
            anim.tween(1.0, 0.0, self._ms(350), self.net.set_reveal)
        self._later(300, lambda: anim.tween(1.0, 0.0, self._ms(450), self._set_bg))
        self._later(860, self._landed)

    def _set_bg(self, v) -> None:
        self.bg = float(v)
        self.update()

    def _landed(self) -> None:
        self.phase = "landed"
        self._later(150, self._done)

    def _done(self) -> None:
        self.phase = "done"
        ri = self._rail_icon()
        if ri is not None:
            ri.show()
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def mousePressEvent(self, e):  # noqa: N802
        if self.phase == "loading" and self.ready():
            self.phase = "settle"

    def paintEvent(self, e):  # noqa: N802
        if self.bg <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.bg)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 18, 18)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor("#0F1A2E"))
        g.setColorAt(1, QColor("#0A101D"))
        p.fillPath(clip, g)
