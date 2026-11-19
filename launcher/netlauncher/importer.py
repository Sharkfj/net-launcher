"""Find PineconeMC / Prism instances and copy one into the launcher."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

LAUNCHER_DIRS = ("ElyPrismLauncher", "PrismLauncher")
SKIP = {"logs", "crash-reports", "downloads", "telemetry", ".cache"}
LOADER_UIDS = {"net.neoforged": "neoforge", "net.fabricmc.fabric-loader": "fabric",
               "net.minecraftforge": "forge", "org.quiltmc.quilt-loader": "quilt"}


def _bases() -> list[Path]:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return [root / d / "instances" for d in LAUNCHER_DIRS]


def find_instances() -> list[Path]:
    out = []
    for base in _bases():
        if base.is_dir():
            out.extend(sorted(p for p in base.iterdir() if (p / "instance.cfg").is_file()))
    return out


def read_versions(inst: Path) -> tuple[str, str, str]:
    data = json.loads((Path(inst) / "mmc-pack.json").read_text(encoding="utf-8"))
    mc, loader, lv = "", "vanilla", ""
    for c in data.get("components") or []:
        uid = c.get("uid", "")
        if uid == "net.minecraft":
            mc = c.get("version", "")
        elif uid in LOADER_UIDS:
            loader, lv = LOADER_UIDS[uid], c.get("version", "")
    return mc, loader, lv


def import_instance(inst: Path, game_dir: Path, progress=None) -> None:
    src = Path(inst) / "minecraft"
    if not src.is_dir():
        src = Path(inst) / ".minecraft"
    game_dir = Path(game_dir)
    game_dir.mkdir(parents=True, exist_ok=True)
    items = [p for p in src.iterdir() if p.name not in SKIP]
    for n, p in enumerate(items, 1):
        target = game_dir / p.name
        if p.is_dir():
            shutil.copytree(p, target, dirs_exist_ok=True, symlinks=True)
        else:
            shutil.copy2(p, target)
        if progress:
            progress(p.name, n, len(items))
