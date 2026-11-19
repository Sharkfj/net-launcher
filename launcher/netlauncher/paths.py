"""Where the launcher keeps its data on each OS."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR_LINUX = "net-launcher"
APP_DIR_WINDOWS = "NET Launcher"


def data_root() -> Path:
    override = os.environ.get("NET_LAUNCHER_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_WINDOWS
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_LINUX


@dataclass(frozen=True)
class Layout:
    root: Path
    minecraft: Path
    instances: Path
    snapshots: Path
    cache: Path
    settings_file: Path
    accounts_file: Path


def layout(root: Path | None = None) -> Layout:
    r = Path(root) if root is not None else data_root()
    lay = Layout(
        root=r,
        minecraft=r / "minecraft",
        instances=r / "instances",
        snapshots=r / "snapshots",
        cache=r / "cache",
        settings_file=r / "settings.json",
        accounts_file=r / "accounts.json",
    )
    for d in (lay.root, lay.minecraft, lay.instances, lay.snapshots, lay.cache):
        d.mkdir(parents=True, exist_ok=True)
    return lay


def game_dir(lay: Layout, pack_id: str = "net") -> Path:
    return lay.instances / pack_id
