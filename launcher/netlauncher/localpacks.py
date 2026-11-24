"""Packs installed in this launcher: identity, version, worlds."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from netlauncher.catalog import PackEntry
from netlauncher.pack import load_state
from netlauncher.paths import Layout

PACK_FILE = Path(".net") / "pack.json"


@dataclass
class LocalPack:
    id: str
    name: str
    version: str
    mc_version: str
    loader: str
    loader_version: str
    description: str = ""
    server: str = ""
    official: bool = False
    fps: bool = False
    fps_mods: list[str] = field(default_factory=list)
    fps_options: dict = field(default_factory=dict)
    backdrop: str = "studio"
    pose: str = "idle"


_FIELDS = {f.name for f in fields(LocalPack)}


def game_dir(lay: Layout, pack_id: str) -> Path:
    return lay.instances / pack_id


def save(lay: Layout, lp: LocalPack) -> None:
    p = game_dir(lay, lp.id) / PACK_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(lp), ensure_ascii=False, indent=1), encoding="utf-8")


def get(lay: Layout, pack_id: str) -> LocalPack | None:
    gd = game_dir(lay, pack_id)
    try:
        raw = json.loads((gd / PACK_FILE).read_text(encoding="utf-8"))
        data = {k: str(v) for k, v in raw.items() if k in _FIELDS}
        for key, kind in (("official", bool), ("fps", bool), ("fps_mods", list), ("fps_options", dict)):
            if key in raw:
                data[key] = raw[key] if isinstance(raw[key], kind) else kind()
        lp = LocalPack(**data)
    except (OSError, ValueError, TypeError):
        return None
    state = load_state(gd)
    if state and state.get("version"):
        lp.version = state["version"]
    return lp


def list_installed(lay: Layout) -> list[LocalPack]:
    if not lay.instances.is_dir():
        return []
    return [lp for d in sorted(lay.instances.iterdir()) if d.is_dir() and (lp := get(lay, d.name))]


def from_entry(e: PackEntry) -> LocalPack:
    return LocalPack(e.id, e.name, e.version, e.mc_version, e.loader, e.loader_version, e.description, e.server,
                     official=True)


def mod_count(lay: Layout, pack_id: str) -> int:
    d = game_dir(lay, pack_id) / "mods"
    return sum(1 for p in d.glob("*.jar")) if d.is_dir() else 0


def newest_world(lay: Layout, pack_id: str) -> str | None:
    saves = game_dir(lay, pack_id) / "saves"
    if not saves.is_dir():
        return None
    worlds = [d for d in saves.iterdir() if (d / "level.dat").is_file()]
    if not worlds:
        return None
    return max(worlds, key=lambda d: (d / "level.dat").stat().st_mtime).name


def total_ram_mb() -> int:
    if sys.platform == "win32":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(st)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return int(st.ullTotalPhys // (1024 * 1024))
    return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1024 * 1024))


def delete(lay: Layout, pack_id: str, keep_worlds: bool = True) -> Path | None:
    """Remove an installed pack. With keep_worlds its saves move to backups/<pack>/saves-<time>/ first."""
    import shutil
    from datetime import datetime
    gd = game_dir(lay, pack_id)
    kept = None
    saves = gd / "saves"
    if keep_worlds and saves.is_dir() and any(saves.iterdir()):
        kept = lay.backups / pack_id / f"saves-{datetime.now():%Y-%m-%d_%H-%M-%S}"
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(saves), str(kept))
    shutil.rmtree(gd, ignore_errors=True)
    return kept


def locked(lp: LocalPack, settings, catalog) -> bool:
    """Players cannot change official packs; the author (author mode with a GitHub token) can."""
    official = lp.official or (catalog is not None and catalog.get(lp.id) is not None)
    author = bool(getattr(settings, "author_mode", False) and getattr(settings, "github_token", ""))
    return official and not author
