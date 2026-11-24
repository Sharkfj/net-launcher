"""Locally installed interface settings shared by the launcher and its editor."""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULTS = {
    "accent": "#4C9AFF", "text": "#E8EEF8", "muted": "#9AA8BF", "card": "#101828",
    "body_font": "Onest", "title_font": "Oswald", "font_scale": 100, "page_inset": 40, "positions": {},
}
COLORS = ("accent", "text", "muted", "card")
LIMITS = {"font_scale": (85, 120), "page_inset": (16, 64)}


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError("Invalid interface settings")
    values = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
    for key in COLORS:
        if not isinstance(values[key], str) or not re.fullmatch(r"#[a-fA-F0-9]{6}", values[key]):
            raise ValueError(key)
        values[key] = values[key].upper()
    for key, (lo, hi) in LIMITS.items():
        if type(values[key]) is not int or not lo <= values[key] <= hi:
            raise ValueError(key)
    for key in ("body_font", "title_font"):
        if not isinstance(values[key], str) or not 0 < len(values[key].strip()) <= 100:
            raise ValueError(key)
    positions = values["positions"]
    if not isinstance(positions, dict) or len(positions) > 2048:
        raise ValueError("positions")
    for name, pair in positions.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][\w.]{0,160}", name)
                or not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(type(v) is not int or abs(v) > 8192 for v in pair)):
            raise ValueError("positions")
    values["positions"] = {name: list(pair) for name, pair in positions.items() if any(pair)}
    return values


def current_file(root: Path):
    return root / "interface" / "current" / "interface.json"


def read(root: Path):
    try:
        return validate(json.loads(current_file(root).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return validate(DEFAULTS)
