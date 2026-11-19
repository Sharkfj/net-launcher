"""Copies of mods/config taken before every change, with one-click restore."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_PARTS = ("mods", "config", "resourcepacks", "shaderpacks")
META = "meta.json"


@dataclass
class Snapshot:
    id: str
    path: Path
    created: datetime
    reason: str
    size_bytes: int
    parts: list[str]


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _new_dir(root: Path, now: datetime) -> Path:
    base = now.strftime("%Y%m%d-%H%M%S")
    n = 1
    while (root / f"{base}-{n}").exists():
        n += 1
    return root / f"{base}-{n}"


def create(root: Path, game_dir: Path, reason: str, parts=DEFAULT_PARTS) -> Snapshot:
    root, game_dir = Path(root), Path(game_dir)
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    dest = _new_dir(root, now)
    dest.mkdir()
    taken = []
    for part in parts:
        src = game_dir / part
        if src.is_dir():
            shutil.copytree(src, dest / part, symlinks=True)
            taken.append(part)
    meta = {"reason": reason, "created": now.isoformat(timespec="microseconds"), "parts": taken}
    (dest / META).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return Snapshot(dest.name, dest, now, reason, sum(_size(dest / p) for p in taken), taken)


def _load(path: Path) -> Snapshot | None:
    try:
        meta = json.loads((path / META).read_text(encoding="utf-8"))
        created = datetime.fromisoformat(meta["created"])
    except (OSError, ValueError, KeyError):
        return None
    parts = [p for p in meta.get("parts", []) if (path / p).is_dir()]
    return Snapshot(path.name, path, created, meta.get("reason", ""), sum(_size(path / p) for p in parts), parts)


def list_snapshots(root: Path) -> list[Snapshot]:
    root = Path(root)
    if not root.is_dir():
        return []
    snaps = [s for d in root.iterdir() if d.is_dir() and (s := _load(d))]
    return sorted(snaps, key=lambda s: (s.created, s.id), reverse=True)


def restore(root: Path, snap: Snapshot, game_dir: Path) -> Snapshot:
    game_dir = Path(game_dir)
    safety = create(root, game_dir, "Перед откатом")
    for part in snap.parts:
        target = game_dir / part
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(snap.path / part, target, symlinks=True)
    return safety


def delete(snap: Snapshot) -> None:
    shutil.rmtree(snap.path, ignore_errors=True)


def prune(root: Path, keep: int = 20) -> None:
    snaps = list_snapshots(root)
    for s in snaps[max(keep, 1):]:
        delete(s)
