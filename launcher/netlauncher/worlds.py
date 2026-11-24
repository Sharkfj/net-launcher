"""Worlds of a pack (saves/) and their zip backups in backups/<pack>/<world>/, five per world."""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from netlauncher.paths import Layout

KEEP = 5


@dataclass
class World:
    name: str
    path: Path
    size: int
    last_played: float


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def list_worlds(game_dir: Path) -> list[World]:
    saves = game_dir / "saves"
    if not saves.is_dir():
        return []
    out = []
    for d in saves.iterdir():
        level = d / "level.dat"
        if d.is_dir() and level.is_file():
            out.append(World(d.name, d, _size(d), level.stat().st_mtime))
    return sorted(out, key=lambda w: w.last_played, reverse=True)


def _dir(lay: Layout, pack_id: str, world_name: str) -> Path:
    return lay.backups / pack_id / world_name


def taken_at(zip_path: Path) -> datetime | None:
    try:
        return datetime.strptime(zip_path.stem, "%Y-%m-%d_%H-%M-%S_%f")
    except ValueError:
        return None


def backups(lay: Layout, pack_id: str, world_name: str) -> list[Path]:
    """Newest first."""
    d = _dir(lay, pack_id, world_name)
    return sorted(d.glob("*.zip"), reverse=True) if d.is_dir() else []


def backup(lay: Layout, pack_id: str, world: World) -> Path:
    d = _dir(lay, pack_id, world.name)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{datetime.now():%Y-%m-%d_%H-%M-%S_%f}.zip"  # fixed width, so names sort by time
    while dest.exists():
        dest = d / f"{datetime.now():%Y-%m-%d_%H-%M-%S_%f}.zip"
    tmp = dest.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as z:
        for f in sorted(world.path.rglob("*")):
            if f.is_file() and f.name != "session.lock":
                z.write(f, f.relative_to(world.path).as_posix())
    tmp.replace(dest)
    for old in backups(lay, pack_id, world.name)[KEEP:]:
        old.unlink(missing_ok=True)
    return dest


def backup_all(lay: Layout, pack_id: str, game_dir: Path) -> list[Path]:
    return [backup(lay, pack_id, w) for w in list_worlds(game_dir)]


def restore(lay: Layout, pack_id: str, game_dir: Path, zip_path: Path) -> Path:
    """Put a backup back. The current world is backed up first, so a restore can be undone."""
    name = zip_path.parent.name
    target = game_dir / "saves" / name
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            p = Path(n)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"unsafe path in backup: {n}")
        if target.is_dir() and (target / "level.dat").is_file():
            backup(lay, pack_id, World(name, target, 0, 0))
        tmp = target.with_name(target.name + ".restoring")
        shutil.rmtree(tmp, ignore_errors=True)
        z.extractall(tmp)
    shutil.rmtree(target, ignore_errors=True)
    tmp.replace(target)
    return target
