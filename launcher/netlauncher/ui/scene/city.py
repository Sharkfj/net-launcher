"""Pixel-art city for the official .NET pack: a view from a rooftop at night.

Four layers (sky, far, mid, rooftop) are drawn once into small images with a margin around the
visible 295x180 frame, then scaled up without smoothing. Moving parts (rain, windows, smoke, the
train, the airship, lights) are drawn over the scaled layers every frame in layer coordinates.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient

BAYER = [(v + .5) / 16 for v in (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)]


def bayer(x: int, y: int) -> float:
    return BAYER[(y & 3) * 4 + (x & 3)]


def hash3(x: int, y: int, s: int = 0) -> float:
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 4294967296


_colors: dict[str, QColor] = {}


def col(c: str) -> QColor:
    q = _colors.get(c)
    if q is None:
        q = _colors[c] = QColor(c)
    return q


class _Layer:
    def __init__(self, w: int, h: int, ox: int, oy: int):
        self.img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        self.img.fill(Qt.GlobalColor.transparent)
        self.ox, self.oy = ox, oy
        self.p = QPainter(self.img)
        self.p.translate(ox, oy)

    def px(self, x, y, w, h, c: str) -> None:
        self.p.fillRect(QRect(int(x), int(y), int(w), int(h)), col(c))

    def dither_v(self, x: int, y: int, w: int, h: int, c1: str, c2: str) -> None:
        a, b = col(c1).rgba(), col(c2).rgba()
        for j in range(h):
            k = j / max(1, h - 1)
            yy = y + j + self.oy
            if not 0 <= yy < self.img.height():
                continue
            for i in range(w):
                xx = x + i + self.ox
                if 0 <= xx < self.img.width():
                    self.img.setPixel(xx, yy, b if bayer(x + i, y + j) < k else a)

    def done(self) -> QImage:
        self.p.end()
        return self.img


class CityScene:
    LW, LH, SCALE, MARGIN, MARGIN_Y = 295, 180, 4, 18, 10
    CAMERAS = {"home": (0, 0, 0), "packs": (-1.3, -.3, .05), "official": (1.2, -.9, .07),
               "friends": (-.7, .5, .03), "settings": (1.4, .7, .06)}
    AMTS = (0, 4, 9, 18)
    TRACK = 132
    STACKS = ((96, 70, 5), (116, 80, 4), (134, 88, 4))
    BOARD = (152, 82, 24, 12)

    def __init__(self, seed: int = 1):
        self.rng = random.Random(seed)
        self.CW, self.CH = self.LW + 2 * self.MARGIN, self.LH + 2 * self.MARGIN_Y
        self.bot = self.LH + self.MARGIN_Y
        self.windows: list[tuple[int, int, str, str]] = []
        self._layers = [self._sky(), self._far(), self._mid(), self._roof()]
        self.t = 0.0
        self.off: dict[int, float] = {}
        self._flick = 0.0
        self.flash, self.next_flash = 0.0, 9.0
        self.board_dark = 0
        self.smoke: list[list[float]] = []
        self.train_x, self.ship_x = 40.0, 150.0
        self.air = [[30.0, 46, 6.0], [200.0, 58, -4.0], [120.0, 38, 3.0]]
        self.drops = [[self.rng.random(), self.rng.random(), 440 + self.rng.random() * 240, self.rng.random() < .35]
                      for _ in range(130)]
        self.splash: tuple[int, int] | None = None

    # ---------- static layers ----------
    def _layer(self) -> _Layer:
        return _Layer(self.CW, self.CH, self.MARGIN, self.MARGIN_Y)

    def _sky(self) -> QImage:
        L, M, MY = self._layer(), self.MARGIN, self.MARGIN_Y
        bands = ["#060b18", "#0a1122", "#0e162b", "#141c33", "#1b2138", "#242439", "#2d2736"]
        bh = math.ceil((self.LH + MY) * .78 / (len(bands) - 1))
        for i in range(len(bands) - 1):
            L.dither_v(-M, -MY + i * bh, self.CW, bh, bands[i], bands[i + 1])
        L.px(-M, -MY + (len(bands) - 1) * bh, self.CW, self.CH, bands[-1])
        return L.done()

    def _far(self) -> QImage:
        L, M, bot = self._layer(), self.MARGIN, self.bot
        steps = ((176, 72, 90), (186, 50, 70), (198, 32, 46), (211, 19, 20))
        for x, y, w in steps:
            L.px(x, y, w, bot - y, "#141c31")
            L.px(x, y, 1, bot - y, "#1b2540")
            L.px(x, y, w, 1, "#1d2843")
        L.px(220, 6, 2, 13, "#141c31")
        for x, y, w in steps:
            for fy in range(y + 4, bot, 6):
                run = 0
                for fx in range(x + 2, x + w - 2):
                    if run <= 0 and hash3(fx, fy, 3) < .025:
                        run = 3 + int(hash3(fy, fx, 3) * 9)
                    lit = run > 0
                    run -= 1
                    if lit:
                        L.px(fx, fy, 1, 1, "#b07a4a" if hash3(fy, x, 5) < .75 else "#5f7fb4")
        skyline = ((-12, 90, 14), (0, 96, 18), (18, 84, 14), (32, 102, 22), (54, 78, 10), (64, 92, 20), (84, 88, 16),
                   (100, 98, 24), (124, 82, 12), (136, 94, 22), (158, 100, 18), (266, 86, 14), (280, 96, 15), (295, 90, 14))
        for x, y, w in skyline:
            L.px(x, y, w, bot - y, "#11192c")
            for fy in range(y + 3, bot, 4):
                for fx in range(x + 1, x + w - 1, 2):
                    if hash3(fx + 40, fy, 9) < .07:
                        L.px(fx, fy, 1, 1, "#7a6a5a")
        L.px(59, 60, 1, 18, "#11192c")
        L.px(57, 66, 5, 1, "#11192c")
        g = QLinearGradient(0, 90, 0, bot)
        g.setColorAt(0, QColor(38, 47, 72, 0))
        g.setColorAt(1, QColor(38, 47, 72, 140))
        L.p.fillRect(QRectF(-M, 90, self.CW, bot - 90), g)
        return L.done()

    def _building(self, L: _Layer, x, top, w, c, floors, lit_p, seed, warm=.7) -> None:
        bot = self.bot
        L.px(x, top, w, bot - top, c)
        L.px(x, top, w, 1, "#1a2338")
        f = 0
        for fy in range(top + 3, bot - 2, floors):
            if hash3(f, seed, 1) >= .25:
                run = 0
                for fx in range(x + 2, x + w - 2):
                    if run <= 0 and hash3(fx, fy, seed) < lit_p * .45:
                        run = 3 + int(hash3(fy, fx, seed) * 7)
                    lit = run > 0
                    run -= 1
                    if lit:
                        self._window(L, fx, fy, "#c98a52" if hash3(fx, f, seed + 7) < warm else "#6f8fc4", c)
            f += 1

    def _window(self, L: _Layer, x, y, lit: str, base: str) -> None:
        L.px(x, y, 1, 1, lit)
        self.windows.append((x, y, lit, base))

    def _mid(self) -> QImage:
        L, M, bot = self._layer(), self.MARGIN, self.bot
        self._building(L, -10, 84, 16, "#0f1629", 4, .2, 10)
        self._building(L, 6, 76, 40, "#0e1527", 4, .22, 11)
        self._building(L, 46, 92, 26, "#101830", 3, .16, 12, .4)
        L.px(50, 86, 18, 6, "#101830")
        self._building(L, 150, 98, 28, "#0f1629", 4, .2, 14)
        self._building(L, 262, 90, 43, "#0e1527", 4, .25, 15)
        L.px(74, 118, 74, bot - 118, "#0d1424")
        for i in range(6):
            sx = 76 + i * 12
            L.px(sx + 6, 112, 6, 6, "#0d1424")
            for k in range(6):
                L.px(sx, 112 + k, 6 - k, 1, "#121a2e")
            L.px(sx, 112, 1, 6, "#1c2640")
            L.px(sx + 1, 114, 1, 3, "#c98a52")
        for x, y, w in self.STACKS:
            L.px(x, y, w, 118 - y, "#111a2c")
            L.px(x, y + 3, w, 2, "#6b5330")
            L.px(x, y, w, 1, "#1d2740")
        for fx in range(78, 146, 3):
            if hash3(fx, 2, 21) < .5:
                self._window(L, fx, 124, "#c98a52", "#0d1424")
        bx, by, bw, bh = self.BOARD
        L.px(bx + 4, by + bh, 1, 4, "#141c2e")
        L.px(bx + bw - 5, by + bh, 1, 4, "#141c2e")
        self._board(L.p, dark=False)
        t = self.TRACK
        L.px(-M, t + 2, self.CW, 2, "#0b1220")
        L.px(-M, t + 2, self.CW, 1, "#18213a")
        for x in range(-6, self.LW + M, 34):
            L.px(x, t + 4, 3, bot - t, "#0b1220")
        return L.done()

    def _roof(self) -> QImage:
        L, M, bot = self._layer(), self.MARGIN, self.bot
        roof = 152
        L.px(-M, roof, self.CW, bot - roof, "#070b14")
        L.px(-M, roof, self.CW, 1, "#151d30")
        L.px(-M, roof - 10, self.CW, 1, "#141b2c")
        for x in range(-M + 2, self.LW + M, 11):
            L.px(x, roof - 10, 1, 10, "#10172a")
        L.px(26, roof - 9, 22, 9, "#0d1322")
        L.px(26, roof - 9, 22, 1, "#1a2236")
        for i in range(4):
            L.px(30 + i * 4, roof - 7, 2, 5, "#080c16")
        L.px(250, 58, 2, roof - 58, "#0c1220")
        for y in range(66, roof, 12):
            L.px(247, y, 8, 1, "#0c1220")
        L.px(249, 54, 4, 4, "#0c1220")

        def cable(x0, y0, x1, y1, sag):
            n = abs(x1 - x0)
            for i in range(n + 1):
                t = i / n
                L.px(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + math.sin(math.pi * t) * sag, 1, 1, "#0b1120")
        cable(250, 72, -M, 106, 26)
        cable(251, 78, self.LW + M, 90, 6)
        for i in range(7):
            x = 60 + i * 31 + int(hash3(i, 1) * 10)
            y = roof + 6 + int(hash3(i, 2) * 18)
            L.px(x, y, 10 + int(hash3(i, 3) * 16), 1, "#121a2c")
        return L.done()

    def static_layers(self) -> list[QImage]:
        return list(self._layers)

    # ---------- motion ----------
    def step(self, dt: float) -> None:
        dt = min(max(dt, 0.0), .25)
        self.t += dt
        r = self.rng
        self._flick += dt
        if self._flick > .35:
            self._flick = 0.0
            for _ in range(2):
                self.off[r.randrange(len(self.windows))] = self.t + 3 + r.random() * 9
        for i in [i for i, until in self.off.items() if until < self.t]:
            del self.off[i]
        if self.t > self.next_flash:
            self.flash = 1.0
            self.next_flash = self.t + 18 + r.random() * 18
        self.flash *= .86 ** (dt * 30)
        self.board_dark = 6 if r.random() < .015 else max(0, self.board_dark - 1)
        if r.random() < .18:
            for x, y, w in self.STACKS:
                self.smoke.append([x + w / 2 + (r.random() - .5) * 2, y - 1, 1.5, .55, 2 + r.random() * 2, -4 - r.random() * 3])
        for s in self.smoke:
            s[0] += s[4] * dt
            s[1] += s[5] * dt
            s[2] += 1.6 * dt
            s[3] -= .1 * dt
        self.smoke = [s for s in self.smoke if s[3] > 0]
        self.train_x += 16 * dt
        if self.train_x > self.LW + 30:
            self.train_x = -200.0
        self.ship_x -= 2.4 * dt
        if self.ship_x < -30:
            self.ship_x = self.LW + 12.0
        for a in self.air:
            a[0] += a[2] * dt
            if a[0] > self.LW + self.MARGIN:
                a[0] = -self.MARGIN
            if a[0] < -self.MARGIN:
                a[0] = self.LW + self.MARGIN
        for d in self.drops:
            d[1] += d[2] * dt * (1.6 if d[3] else 1) / 720
            d[0] -= d[2] * .3 * dt / 1180
            if d[1] > 1:
                d[1] -= 1.02
                d[0] = r.random() * 1.15
        self.splash = (r.randrange(self.LW), 153 + r.randrange(26)) if r.random() < .5 else None

    # ---------- drawing ----------
    @staticmethod
    def _rect(p: QPainter, x, y, w, h, c: str) -> None:
        p.fillRect(QRect(int(x), int(y), int(w), int(h)), col(c))

    def _board(self, p: QPainter, dark: bool) -> None:
        bx, by, bw, bh = self.BOARD
        self._rect(p, bx, by, bw, bh, "#18263f" if dark else "#22406a")
        if not dark:
            self._rect(p, bx + 3, by + 3, 6, 6, "#9fc4f2")
            self._rect(p, bx + 11, by + 4, 10, 1, "#9fc4f2")
            self._rect(p, bx + 11, by + 7, 7, 1, "#6f8fc4")

    def _dyn_sky(self, p: QPainter) -> None:
        if self.flash > .03:
            g = QLinearGradient(0, -self.MARGIN_Y, 0, 110)
            g.setColorAt(0, QColor(80, 96, 140, int(self.flash * 115)))
            g.setColorAt(1, QColor(80, 96, 140, 0))
            p.fillRect(QRectF(-self.MARGIN, -self.MARGIN_Y, self.CW, 115), g)
        for x, y, v in self.air:
            self._rect(p, x, y, 1, 1, "#f2e6d2")
            self._rect(p, x - (1 if v > 0 else -1), y, 1, 1, "#7d7466")

    def _dyn_far(self, p: QPainter) -> None:
        if int(self.t * 1.1) % 2 == 0:
            self._rect(p, 220, 5, 2, 1, "#ff5a4a")
        x, y = round(self.ship_x), 40 + round(math.sin(self.t * .4))
        for i, (o, w) in enumerate(((5, 10), (2, 16), (1, 18), (1, 18), (2, 16), (5, 10))):
            self._rect(p, x + o, y + i, w, 1, "#2c3850" if i < 2 else "#212b40")
        self._rect(p, x + 7, y + 6, 6, 2, "#182030")
        self._rect(p, x + 8, y + 6, 1, 1, "#e0a865")
        self._rect(p, x + 11, y + 6, 1, 1, "#e0a865")
        if self.t % 1.8 < .2:
            self._rect(p, x + 19, y + 2, 1, 1, "#ff5a4a")

    def _dyn_mid(self, p: QPainter) -> None:
        for i in self.off:
            x, y, _lit, base = self.windows[i]
            self._rect(p, x, y, 1, 1, base)
        if self.board_dark:
            self._board(p, dark=True)
        for x, y, rad, a, _vx, _vy in self.smoke:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(62, 70, 92, int(a * .5 * 255)))
            p.drawEllipse(QPointF(x, y), rad, rad)
        t, x0 = self.TRACK, self.train_x
        for i in range(5):
            cx = round(x0 + i * 19)
            self._rect(p, cx, t - 4, 18, 5, "#262f43")
            self._rect(p, cx, t - 4, 18, 1, "#323c53")
            for k in range(2, 17, 3):
                self._rect(p, cx + k, t - 2, 2, 1, "#e0a865")
            self._rect(p, cx + 2, t + 1, 2, 1, "#0a0f1a")
            self._rect(p, cx + 14, t + 1, 2, 1, "#0a0f1a")
        hx = round(x0 + 5 * 19)
        self._rect(p, hx - 1, t - 3, 2, 2, "#f4d7a8")
        g = QRadialGradient(hx + 3, t - 2, 12)
        g.setColorAt(0, QColor(244, 215, 168, 90))
        g.setColorAt(1, QColor(244, 215, 168, 0))
        p.fillRect(QRectF(hx - 9, t - 14, 24, 24), g)
        f = QLinearGradient(0, 110, 0, self.bot)
        f.setColorAt(0, QColor(30, 38, 57, 0))
        f.setColorAt(1, QColor(30, 38, 57, 90))
        p.fillRect(QRectF(-self.MARGIN, 110, self.CW, self.bot - 110), f)

    def _dyn_roof(self, p: QPainter) -> None:
        if int(self.t * .9) % 2 == 0:
            self._rect(p, 250, 53, 2, 1, "#ff5a4a")
        if self.splash:
            self._rect(p, self.splash[0], self.splash[1], 1, 1, "#3a4660")

    def render(self, p: QPainter, size: QSize, parallax: QPointF, cam: tuple[float, float, float]) -> None:
        w, h = size.width(), size.height()
        s = max(h / self.LH, w / self.LW)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        dyn = (self._dyn_sky, self._dyn_far, self._dyn_mid, self._dyn_roof)
        for img, amt, draw in zip(self._layers, self.AMTS, dyn):
            sl = s * (1 + cam[2] * amt / 9)
            x0 = (w - self.CW * sl) / 2 - (parallax.x() + cam[0]) * amt
            y0 = (h - self.CH * sl) / 2 - (parallax.y() + cam[1]) * amt * .5
            p.save()
            p.translate(x0, y0)
            p.scale(sl, sl)
            p.drawImage(0, 0, img)
            p.translate(self.MARGIN, self.MARGIN_Y)
            draw(p)
            p.restore()
        block = max(2, round(s))
        for x, y, _v, near in self.drops:
            p.fillRect(QRect(int(x * w) // block * block, int(y * h) // block * block, block, block * (3 if near else 2)),
                       col("#4a5672" if near else "#2f3a54"))
        p.restore()
