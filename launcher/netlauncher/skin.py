"""Ely.by skins: download with cache, and the Minecraft player-model box layout (Qt-free)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from netlauncher.net import Http, HttpError, Offline

TEXTURES = "https://skinsystem.ely.by/textures/{name}"
CACHE_TTL = 3600


@dataclass(frozen=True)
class Skin:
    png: bytes
    slim: bool


SIZE_ERROR = "Нужна картинка PNG размером 64×64 или 64×32."


def png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(SIZE_ERROR)
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def check_skin(data: bytes) -> tuple[int, int]:
    size = png_size(data)
    if size not in ((64, 64), (64, 32)):
        raise ValueError(SIZE_ERROR)
    return size


def fetch(http: Http, name: str, cache_dir: Path, force: bool = False) -> Skin | None:
    if not re.fullmatch(r"[A-Za-z0-9_]{2,16}", name):
        return None
    def texture():
        info = http.get_json(TEXTURES.format(name=name)) or {}
        sk = info.get("SKIN") if isinstance(info, dict) else None
        if sk and sk.get("url"):
            return sk["url"], (sk.get("metadata") or {}).get("model") == "slim"
        return None

    return fetch_texture(http, name, cache_dir, force, texture)


def fetch_texture(http, name, cache_dir, force, texture):
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", name):
        return None
    d = Path(cache_dir) / "skins"
    png, meta = d / f"{name}.png", d / f"{name}.json"

    def cached() -> Skin | None:
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            if m.get("none"):
                return None
            return Skin(png.read_bytes(), bool(m.get("slim")))
        except (OSError, ValueError):
            return None

    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
        if not force and time.time() - float(m.get("fetched", 0)) < CACHE_TTL:
            return cached()
    except (OSError, ValueError):
        pass
    try:
        resource = texture()
        d.mkdir(parents=True, exist_ok=True)
        if not resource:
            meta.write_text(json.dumps({"fetched": time.time(), "none": True}), encoding="utf-8")
            return None
        url, slim = resource
        http.download(url, png)
        meta.write_text(json.dumps({"fetched": time.time(), "slim": slim}), encoding="utf-8")
        return Skin(png.read_bytes(), slim)
    except (Offline, HttpError, OSError, ValueError):
        return cached()


@dataclass
class Box:
    size: tuple[float, float, float]      # w, h, d (pixels)
    origin: tuple[float, float, float]    # min corner x, y, z; y up from the feet, front faces +z
    uv: tuple[int, int]
    mirror: bool = False
    inflate: float = 0.0
    overlay: "Box | None" = None
    pivot: tuple[float, float, float] | None = None  # rotation point for limbs


def parts(width: int, height: int, slim: bool) -> dict[str, Box]:
    legacy = height < 64
    aw = 3 if slim else 4

    def ov(base: Box, uv: tuple[int, int], inflate: float) -> Box:
        return Box(base.size, base.origin, uv, False, inflate, None, base.pivot)

    head = Box((8, 8, 8), (-4, 24, -4), (0, 0))
    head.overlay = ov(head, (32, 0), 0.5)
    body = Box((8, 12, 4), (-4, 12, -2), (16, 16))
    arm_r = Box((aw, 12, 4), (-4 - aw, 12, -2), (40, 16), pivot=(-4 - aw / 2, 22, 0))
    leg_r = Box((4, 12, 4), (-4, 0, -2), (0, 16), pivot=(-2, 12, 0))
    if legacy:
        arm_l = Box((aw, 12, 4), (4, 12, -2), (40, 16), mirror=True, pivot=(4 + aw / 2, 22, 0))
        leg_l = Box((4, 12, 4), (0, 0, -2), (0, 16), mirror=True, pivot=(2, 12, 0))
    else:
        arm_l = Box((aw, 12, 4), (4, 12, -2), (32, 48), pivot=(4 + aw / 2, 22, 0))
        leg_l = Box((4, 12, 4), (0, 0, -2), (16, 48), pivot=(2, 12, 0))
        body.overlay = ov(body, (16, 32), 0.25)
        arm_r.overlay = ov(arm_r, (40, 32), 0.25)
        arm_l.overlay = ov(arm_l, (48, 48), 0.25)
        leg_r.overlay = ov(leg_r, (0, 32), 0.25)
        leg_l.overlay = ov(leg_l, (0, 48), 0.25)
    return {"leg_r": leg_r, "leg_l": leg_l, "body": body, "arm_r": arm_r, "arm_l": arm_l, "head": head}


Vec = tuple[float, float, float]


def faces(b: Box) -> list[tuple[str, list[Vec], tuple[int, int, int, int], Vec]]:
    """Six faces: (name, corners TL,TR,BR,BL as seen from outside, texture rect u,v,w,h, outward normal)."""
    w, h, d = b.size
    i = b.inflate
    x0, y0, z0 = b.origin[0] - i, b.origin[1] - i, b.origin[2] - i
    x1, y1, z1 = b.origin[0] + w + i, b.origin[1] + h + i, b.origin[2] + d + i
    u, v = b.uv
    tw, th, td = int(w), int(h), int(d)
    rect = {
        "top": (u + td, v, tw, td),
        "bottom": (u + td + tw, v, tw, td),
        "right": (u, v + td, td, th),
        "front": (u + td, v + td, tw, th),
        "left": (u + td + tw, v + td, td, th),
        "back": (u + 2 * td + tw, v + td, tw, th),
    }
    if b.mirror:
        rect["right"], rect["left"] = rect["left"], rect["right"]
    out = [
        ("front", [(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)], (0, 0, 1)),
        ("back", [(x1, y1, z0), (x0, y1, z0), (x0, y0, z0), (x1, y0, z0)], (0, 0, -1)),
        ("right", [(x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (x0, y0, z0)], (-1, 0, 0)),
        ("left", [(x1, y1, z1), (x1, y1, z0), (x1, y0, z0), (x1, y0, z1)], (1, 0, 0)),
        ("top", [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0, 1, 0)),
        ("bottom", [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)], (0, -1, 0)),
    ]
    result = []
    for name, corners, normal in out:
        if b.mirror:
            corners = [corners[1], corners[0], corners[3], corners[2]]
        result.append((name, corners, rect[name], normal))
    return result
