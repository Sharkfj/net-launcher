""".N icon: a wide N (Unbounded) with a blue drop at its foot, plus the splash animation.

72 frames (2.4 s at 30 fps): the drop drains into the N, a blue wave flows through the letter
(up the left stroke, down the diagonal, up the right stroke) and mixes with the white, then the drop
fills up again at the foot. Frame 0 is the rest pose (also icon.png). Needs Pillow; run from the
launcher folder:
    .venv/bin/python tools/render_icon2d.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageChops, ImageDraw, ImageFilter  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QPainter, QPainterPath  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "netlauncher" / "ui" / "assets" / "icon"
FONT = HERE / "fonts" / "Unbounded.ttf"
FRAMES = 72
SS = 2
TOP, BOTTOM, BLUE = (240, 245, 255), (176, 198, 240), (76, 154, 255)


def to_pil(img: QImage) -> Image.Image:
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA", 0, 1).convert("L")


def smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def timeline(f: int) -> tuple[float, float]:
    """(drop size 0..1, wave centre along the N 0..1) for frame f."""
    t = f / FRAMES
    if t < .08:
        drop = 1.0
    elif t < .3:
        drop = 1 - .62 * smooth((t - .08) / .22)
    elif t < .72:
        drop = .38
    else:
        drop = .38 + .62 * smooth((t - .72) / .25)
    wave = -.35 + 1.75 * smooth((t - .1) / .62)
    return drop, wave


class Glyph:
    """The N at one size: its mask, its skeleton and, for every pixel, how far along the skeleton it lies."""

    def __init__(self, big: int):
        font = QFont("Unbounded")
        font.setPixelSize(int(big * .56))
        font.setVariableAxis(QFont.Tag("wght"), 800)
        fm = QFontMetricsF(font)
        path = QPainterPath()
        path.addText(QPointF(big * .6 - fm.horizontalAdvance("N") / 2, big * .5 + fm.capHeight() / 2), font, "N")
        path.setFillRule(Qt.FillRule.WindingFill)
        self.path = path.simplified()
        self.br = self.path.boundingRect()
        img = QImage(big, big, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillPath(self.path, QColor(255, 255, 255))
        p.end()
        self.mask = to_pil(img)
        br, sw = self.br, self.br.width() * .3
        pts = [(br.left() + sw / 2, br.bottom()), (br.left() + sw / 2, br.top()), (br.right() - sw / 2, br.bottom()),
               (br.right() - sw / 2, br.top())]
        segs = list(zip(pts, pts[1:]))
        lens = [math.dist(a, b) for a, b in segs]
        total = sum(lens)
        umap = Image.new("L", (big, big), 0)
        px, m = umap.load(), self.mask.load()
        for y in range(big):
            for x in range(big):
                if m[x, y] < 8:
                    continue
                best, bu, acc = 1e18, 0.0, 0.0
                for (a, b), ln in zip(segs, lens):
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / (ln * ln)))
                    d = (x - a[0] - dx * k) ** 2 + (y - a[1] - dy * k) ** 2
                    if d < best:
                        best, bu = d, (acc + k * ln) / total
                    acc += ln
                px[x, y] = round(bu * 255)
        self.umap = umap


def frame(g: Glyph, big: int, size: int, f: int, white: Image.Image, blue: Image.Image, *, tray=False) -> Image.Image:
    drop, wave = timeline(f)
    br = g.br
    r0 = br.width() * .14
    r = r0 * drop
    cx, cy = br.left() - r0 * .95 + (r0 - r) * .9, br.bottom() - r
    d_img = QImage(big, big, QImage.Format.Format_ARGB32)
    d_img.fill(QColor(0, 0, 0))
    p = QPainter(d_img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.end()
    n, d = g.mask, to_pil(d_img)
    goo = ImageChops.lighter(n, d).filter(ImageFilter.GaussianBlur(r0 * .45)).point(lambda v: 255 if v > 118 else 0)
    region = Image.new("L", n.size, 0)
    ImageDraw.Draw(region).ellipse((cx - r0 * 2.4, cy - r0 * 2.0, br.left() + r0 * 2.2, cy + r0 * 1.6), fill=255)
    region = region.filter(ImageFilter.GaussianBlur(r0 * .6))
    alpha = ImageChops.lighter(ImageChops.lighter(n, d), ImageChops.multiply(goo, region)).filter(ImageFilter.GaussianBlur(1.0))
    # the blue wave along the letter, with soft mixing edges
    lut = [round(255 * math.exp(-((v / 255 - wave) / .2) ** 2)) for v in range(256)]
    band = g.umap.point(lut)
    # the drop's own blue spreading into the foot
    tint = Image.new("L", (big, big), 0)
    reach = r0 * (1.6 + 1.6 * drop)
    halo = Image.radial_gradient("L").resize((round(reach * 2), round(reach * 2)))
    tint.paste(ImageChops.invert(halo), (round(cx - reach), round(cy - reach)))
    tint = tint.point(lambda v: round(255 * (v / 255) ** 1.4 * drop))
    mixmask = ImageChops.lighter(band, ImageChops.lighter(tint, d))
    colour = Image.composite(blue, white, mixmask)
    if tray:
        colour.putalpha(alpha)
        mark = colour.crop(alpha.getbbox())
        mark.thumbnail((size - 4, size - 4), Image.LANCZOS)
        square = Image.new("RGBA", (size, size))
        square.paste(mark, ((size - mark.width) // 2, (size - mark.height) // 2))
        return square
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    m = Image.new("L", (big, big), 0)
    ImageDraw.Draw(m).rounded_rectangle((4 * SS, 4 * SS, big - 4 * SS, big - 4 * SS), radius=int(big * .22), fill=255)
    tile.paste((13, 21, 38, 255), (0, 0), m)
    tile.paste(colour, (0, 0), alpha)
    return tile.resize((size, size), Image.LANCZOS)


def layers(big: int) -> tuple[Image.Image, Image.Image]:
    white = Image.new("RGB", (big, big))
    blue = Image.new("RGB", (big, big))
    dw, db = ImageDraw.Draw(white), ImageDraw.Draw(blue)
    for y in range(big):
        t = y / big
        dw.line([(0, y), (big, y)], fill=tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)))
        db.line([(0, y), (big, y)], fill=tuple(round(c * (1.08 - .16 * t)) if c < 200 else 255 for c in BLUE))
    return white, blue


def main() -> None:
    QGuiApplication(sys.argv)
    if QFontDatabase.addApplicationFont(str(FONT)) < 0:
        sys.exit(f"cannot load {FONT}")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in list(OUT.glob("spin_*.png")) + list(OUT.glob("frame_*.png")):
        old.unlink()
    big = 256 * SS
    g, (white, blue) = Glyph(big), layers(big)
    frame(g, big, 128, 0, white, blue, tray=True).save(OUT / "tray.png", optimize=True)
    for f in range(FRAMES):
        frame(g, big, 256, f, white, blue).save(OUT / f"frame_{f:02d}.png", optimize=True)
    big = 512 * SS
    frame(Glyph(big), big, 512, 0, *layers(big)).save(OUT / "icon.png", optimize=True)
    print(f"wrote {FRAMES} frames and icon.png to {OUT}")


if __name__ == "__main__":
    main()
