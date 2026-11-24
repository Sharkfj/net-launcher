"""Interactive 3D player model drawn with QPainter (orthographic, painter's algorithm)."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPolygonF, QRadialGradient,
                           QTransform)
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


# ---------------------------------------------------------------- scene renderer
from collections import namedtuple  # noqa: E402

from netlauncher.ui.scene.springs import Spring, Springs  # noqa: E402

ProjFace = namedtuple("ProjFace", "part name layer depth poly uv light glows")

_CENTER_Y = 16.0
# Arcane-like lighting: dark cool base, warm key from the front left, a hard cool rim from the back right.
_AMBIENT = (.30, .29, .41)
_KEY = ((-50.0, 40.0, 45.0), (1.0, .79, .61), .82)      # position, colour, strength (fill tint)
_RIM = ((62.0, 24.0, -38.0), (.38, .79, .94), 1.68)       # painted as an additive glow from the lit edge
_WARM = ((-50.0, 40.0, 45.0), (1.0, .66, .42), .45)     # soft warm highlight on faces turned to the key
_IDLE = {"hx": .1, "hy": 0.0, "hz": .03, "rax": .1, "raz": -.07, "lax": -.08, "laz": .07,
         "rlx": 0.0, "rlz": -.07, "llx": 0.0, "llz": .07, "ry": -.42, "py": 0.0}
_REACTIONS = {"idle", "ready", "turn_head", "check", "nod"}


def _rot_z(p, a):
    c, s = math.cos(a), math.sin(a)
    x, y, z = p
    return x * c - y * s, x * s + y * c, z


def _norm(v):
    ln = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return v[0] / ln, v[1] / ln, v[2] / ln


def _cross(a, b):
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class SkinRenderer:
    """The player's skin as it stands in the studio scene: perspective camera, coloured lights, spring poses."""

    CAMERAS = {"home": (8.7, -7.9, 94, 4), "packs": (26.6, 0.9, 62.6, 9), "official": (2.7, -15.9, 87.4, 6),
               "friends": (-15.6, -4.5, 89.6, 3), "settings": (19.2, 2.3, 48.7, 11)}
    POSES = {"home": {"ry": -.42}, "packs": {"ry": -2.25, "hy": -.28, "hx": .16}, "official": {"ry": -1.35, "hy": 0.0, "hx": .04},
             "friends": {"ry": -.08, "hy": .1, "hx": .08, "hz": .08, "llz": .14}, "settings": {"ry": -.85, "hy": -.15, "hx": .26}}
    FOV = 28.0

    def __init__(self, skin: Skin | None = None):
        self.tab = "home"
        self.reaction = "idle"
        self.style_pose = "idle"
        self._since = 0.0
        self.t = 0.0
        self._look = (0.0, 0.0)
        self.pose = Springs(dict(_IDLE), k={"hx": 22, "hy": 22, "hz": 18, "ry": 9}, damping={"hx": .85, "hy": .85})
        yaw, pitch, dist, th = self.CAMERAS["home"]
        self.cam = Springs({"yaw": yaw, "pitch": pitch, "dist": dist, "th": th}, default_k=5.5)
        self._tiles: dict = {}
        self._cache: QImage | None = None
        self._cache_skin = None
        self.renders = 0
        self.set_skin(skin)

    # ---------- api ----------
    def set_skin(self, sk: Skin | None) -> None:
        sk = sk or default_skin()
        img = QImage.fromData(sk.png)
        if img.isNull() or img.width() != 64 or img.height() not in (32, 64):
            sk = default_skin()
            img = QImage.fromData(sk.png)
        self._img = img.convertToFormat(QImage.Format.Format_ARGB32)
        self.skin_png, self.slim = sk.png, sk.slim
        self._parts = parts(64, self._img.height(), sk.slim)
        self._geometry = {}
        for name, base in self._parts.items():
            layers = []
            for layer, box in (("base", base), ("overlay", base.overlay)):
                if box is None:
                    continue
                for face_name, corners, uv, normal in faces(box):
                    x, y, w, h = uv
                    if layer == "overlay" and not any(self._img.pixel(i, j) >> 24
                                                      for j in range(y, y+h) for i in range(x, x+w)):
                        continue
                    layers.append((layer, face_name, corners, uv, normal))
            self._geometry[name] = layers
        self._tiles = {}

    def set_style_pose(self, pose: str) -> None:
        if self.style_pose == pose:
            return
        self.style_pose = pose
        from netlauncher.ui import anim
        if not anim.enabled():
            self.pose.snap(self._targets())
            self._cache = None

    def set_tab(self, name: str) -> None:
        self.tab = name if name in self.CAMERAS else "home"
        yaw, pitch, dist, th = self.CAMERAS[self.tab]
        self.cam.set_targets({"yaw": yaw, "pitch": pitch, "dist": dist, "th": th})

    def react(self, name: str) -> None:
        if name not in _REACTIONS:
            raise ValueError(name)
        self.reaction, self._since = name, 0.0

    def look_at(self, x: float, y: float) -> None:
        self._look = (max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y)))

    def moving(self) -> bool:
        return self.cam.moving(.01) or self.pose.moving(.002)

    def camera(self) -> tuple[float, float, float, float]:
        return self.cam["yaw"], self.cam["pitch"], self.cam["dist"], self.cam["th"]

    # ---------- motion ----------
    def _targets(self) -> dict[str, float]:
        T = dict(_IDLE)
        breath = math.sin(self.t * 1.25)
        T["raz"] -= breath * .012
        T["laz"] += breath * .012
        T["py"] = breath * .05
        if self.tab == "home":
            if self.style_pose == "wave":
                T.update(rax=-2.55, raz=-.42 + breath * .08, laz=.14, ry=-.26)
            elif self.style_pose == "stride":
                T.update(rlx=.58, llx=-.44, rax=-.65, lax=.51, ry=-.67)
            mx = (self._look[0] + 1) / 2 * 1180
            my = (self._look[1] + 1) / 2 * 720
            T["hy"] = max(-.34, min(.34, (mx - 950) / 1300))
            T["hx"] = .1 + max(-.12, min(.18, (my - 230) / 1400))
        else:
            T.update(self.POSES[self.tab])
        r, since = self.reaction, self._since
        if r == "ready":
            T.update(hy=-.32, hx=.14, ry=-.5)
        elif r == "turn_head":
            T.update(hy=-.5, hx=.06)
            if since > 1.2:
                self.reaction = "idle"
        elif r == "check":
            T.update(hx=.38, hy=-.1, rax=-.55, raz=-.02)
        elif r == "nod":
            T["hx"] = .32 if since < .25 else .08
            if since > .7:
                self.reaction = "idle"
        return T

    def step(self, dt: float) -> None:
        dt = min(max(dt, 0.0), .25)
        self.t += dt
        self._since += dt
        self.pose.set_targets(self._targets())
        self.pose.step(dt)
        self.cam.step(dt)

    # ---------- geometry ----------
    def _view(self):
        yaw, pitch, dist, th = self.camera()
        target = (0.0, _CENTER_Y + th, 0.0)
        ya, pa = math.radians(yaw), math.radians(pitch)
        d = (math.sin(ya) * math.cos(pa), math.sin(pa), math.cos(ya) * math.cos(pa))
        eye = (target[0] + d[0] * dist, target[1] + d[1] * dist, target[2] + d[2] * dist)
        f = _norm((target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]))
        r = _norm(_cross(f, (0.0, 1.0, 0.0)))
        u = _cross(r, f)
        return eye, f, r, u

    def _transform(self, name, pivot):
        pose = self.pose
        x = y = z = 0.
        if name == "head":
            x, y, z = pose["hx"], pose["hy"], pose["hz"]
            pivot = (0., 24., 0.)
        elif pivot is not None:
            prefix = {"arm_r": "ra", "arm_l": "la", "leg_r": "rl", "leg_l": "ll"}[name]
            x, z = pose[prefix + "x"], pose[prefix + "z"]

        def rotate(v):
            return _rot_y(_rot_x(_rot_y(_rot_z(v, z), y), x), pose["ry"])

        a, b, c = (rotate(axis) for axis in ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)))
        pivot = pivot or (0., 0., 0.)
        origin = _rot_y(pivot, pose["ry"])
        offset = rotate(pivot)
        dx, dy, dz = origin[0]-offset[0], origin[1]-offset[1]+pose["py"], origin[2]-offset[2]

        def transform(v, point):
            x, y, z = v
            return (a[0]*x + b[0]*y + c[0]*z + dx*point,
                    a[1]*x + b[1]*y + c[1]*z + dy*point,
                    a[2]*x + b[2]*y + c[2]*z + dz*point)
        return transform

    @staticmethod
    def _dir(light, center):
        pos = light[0]
        return _norm((pos[0] - center[0], pos[1] + _CENTER_Y - center[1], pos[2] - center[2]))

    def _light(self, center, n) -> tuple[float, float, float]:
        k = max(0.0, _dot(n, self._dir(_KEY, center)))
        out = [_AMBIENT[i] + k * _KEY[2] * _KEY[1][i] for i in range(3)]
        top = max(out)
        if top > 1.0:  # keep the hue: scale all channels instead of clipping each
            out = [v / top for v in out]
        return tuple(out)

    def _glows(self, center, n, poly: list[QPointF], to_screen) -> list:
        """Additive light gradients across a face: (rgb, strength, bright point, dark point)."""
        out = []
        for light, power, reach in ((_RIM, 1.0, .5), (_WARM, 2.0, .7)):
            d = self._dir(light, center)
            k = max(0.0, _dot(n, d)) ** power * light[2]
            if k < .04:
                continue
            a, b = to_screen(center), to_screen((center[0] + d[0] * 6, center[1] + d[1] * 6, center[2] + d[2] * 6))
            dx, dy = b.x() - a.x(), b.y() - a.y()
            ln = math.hypot(dx, dy)
            if ln < 1e-3:
                continue
            dx, dy = dx / ln, dy / ln
            proj = [q.x() * dx + q.y() * dy for q in poly]
            hi, lo = max(proj), min(proj)
            ref = poly[proj.index(hi)]
            start = QPointF(ref.x(), ref.y())
            end = QPointF(ref.x() - dx * (hi - lo) * reach, ref.y() - dy * (hi - lo) * reach)
            out.append((light[1], k, start, end))
        return out

    def projected(self, rect: QRectF) -> list[ProjFace]:
        eye, f, r, u = self._view()
        focal = rect.height() / 2 / math.tan(math.radians(self.FOV / 2))
        cx, cy = rect.center().x(), rect.center().y()
        out = []
        def to_screen(q):
            v = (q[0] - eye[0], q[1] - eye[1], q[2] - eye[2])
            scale = focal / max(1e-3, _dot(v, f))
            return QPointF(cx + _dot(v, r) * scale, cy - _dot(v, u) * scale)

        for name, geometry in self._geometry.items():
            transform = self._transform(name, self._parts[name].pivot)
            points = {}
            for layer, fname, corners, uv, normal in geometry:
                n = transform(normal, False)
                first = transform(corners[0], True)
                if _dot(n, (eye[0]-first[0], eye[1]-first[1], eye[2]-first[2])) <= 1e-6:
                    continue
                for corner in corners:
                    if corner not in points:
                        points[corner] = transform(corner, True)
                pts = [points[q] for q in corners]
                c = tuple((a+b)*.5 for a,b in zip(pts[0], pts[2]))
                screen = [to_screen(q) for q in pts]
                depth = _dot((c[0]-eye[0], c[1]-eye[1], c[2]-eye[2]), f)
                depth -= .01 if layer == "overlay" else 0
                out.append(ProjFace(name, fname, layer, depth, QPolygonF(screen), uv, self._light(c, n),
                                    self._glows(c, n, screen, to_screen)))
        out.sort(key=lambda fc: -fc.depth)
        return out

    # ---------- painting ----------
    def _tile(self, uv, light) -> QImage:
        u, v, w, h = uv
        key = (u, v, w, h, round(light[0], 2), round(light[1], 2), round(light[2], 2))
        img = self._tiles.get(key)
        if img is None:
            img = self._img.copy(u, v, w, h)
            fr, fg, fb = key[4:]
            for y in range(h):
                for x in range(w):
                    px = img.pixel(x, y)
                    a = px >> 24 & 0xFF
                    if a:
                        img.setPixel(x, y, (a << 24) | (int((px >> 16 & 0xFF) * fr) << 16)
                                     | (int((px >> 8 & 0xFF) * fg) << 8) | int((px & 0xFF) * fb))
            if len(self._tiles) > 4000:
                self._tiles.clear()
            self._tiles[key] = img
        return img

    def _feet(self, rect: QRectF) -> tuple[QPointF, float]:
        eye, f, r, u = self._view()
        focal = rect.height() / 2 / math.tan(math.radians(self.FOV / 2))
        cx, cy = rect.center().x(), rect.center().y()

        def proj(q):
            v = (q[0] - eye[0], q[1] - eye[1], q[2] - eye[2])
            z = max(1e-3, _dot(v, f))
            return QPointF(cx + _dot(v, r) / z * focal, cy - _dot(v, u) / z * focal)
        c, side = proj((0.0, 0.0, 0.0)), proj((7.0, 0.0, 0.0))
        return c, abs(side.x() - c.x()) or 1.0

    _POSE_KEYS = ("hx", "hy", "hz", "rax", "raz", "lax", "laz", "rlx", "rlz", "llx", "llz", "ry", "py")

    def _state(self) -> tuple:
        return tuple(self.pose[k] for k in self._POSE_KEYS) + self.camera()

    def paint(self, p: QPainter, rect: QRectF) -> None:
        """Reuse the last frame while both the camera and pose are still."""
        size = (round(rect.width()), round(rect.height()))
        state = self._state()
        last = getattr(self, "_cache_state", None)
        stale = (self._cache is None or self._cache.width() != size[0] or self._cache.height() != size[1]
                 or self._cache_skin is not self._img or last is None)
        if not stale:
            pose_d = max(abs(a - b) for a, b in zip(state[:13], last[:13]))
            cam_d = max(abs(a - b) for a, b in zip(state[13:], last[13:]))
            stale = pose_d > .0004 or cam_d > .005
        if stale:
            img = QImage(max(1, size[0]), max(1, size[1]), QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            q = QPainter(img)
            self._render(q, QRectF(0, 0, size[0], size[1]))
            q.end()
            self._cache, self._cache_state, self._cache_skin = img, state, self._img
            self.renders += 1
        p.drawImage(rect.topLeft(), self._cache)

    def _render(self, p: QPainter, rect: QRectF) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        feet, rad = self._feet(rect)
        g = QRadialGradient(feet, rad * 1.6)
        g.setColorAt(0, QColor(0, 0, 0, 120))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(feet, rad * 1.6, rad * .45)
        base = p.transform()
        for fc in self.projected(rect):
            u, v, tw, th = fc.uv
            if tw <= 0 or th <= 0:
                continue
            pts = [fc.poly[i] for i in range(4)]
            center = QPointF(sum(q.x() for q in pts) / 4, sum(q.y() for q in pts) / 4)
            grown = []
            for q in pts:
                d = q - center
                ln = math.hypot(d.x(), d.y()) or 1.0
                grown.append(q + d * (0.6 / ln))
            src = QPolygonF([QPointF(0, 0), QPointF(tw, 0), QPointF(tw, th), QPointF(0, th)])
            t = QTransform()
            if not QTransform.quadToQuad(src, QPolygonF(grown), t):
                continue
            p.setTransform(t * base)
            p.drawImage(QRectF(0, 0, tw, th), self._tile(fc.uv, fc.light))
            p.setTransform(base)
            path = QPainterPath()
            path.addPolygon(fc.poly)
            path.closeSubpath()
            if fc.name not in ("top", "bottom"):
                br = fc.poly.boundingRect()
                shade = QLinearGradient(br.topLeft(), br.bottomLeft())
                shade.setColorAt(0, QColor(255, 255, 255, 0))
                shade.setColorAt(1, QColor(0, 0, 10, 70))
                p.fillPath(path, shade)
            if fc.glows:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                for (cr, cg, cb), k, start, end in fc.glows:
                    gl = QLinearGradient(start, end)
                    a = max(0, min(255, round(255 * k * .8)))
                    gl.setColorAt(0, QColor(round(cr * a), round(cg * a), round(cb * a), a))
                    gl.setColorAt(1, QColor(0, 0, 0, 0))
                    p.fillPath(path, gl)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setTransform(base)
        p.restore()
