"""Create your own packs: pick a Minecraft version and a mod loader."""

from __future__ import annotations

import minecraft_launcher_lib.mod_loader as mll_mod_loader
import minecraft_launcher_lib.utils as mll_utils

from netlauncher import localpacks
from netlauncher.author import new_pack_id
from netlauncher.localpacks import LocalPack
from netlauncher.paths import Layout

LOADERS = [("vanilla", "Без модов"), ("fabric", "Fabric"), ("forge", "Forge"), ("neoforge", "NeoForge"),
           ("quilt", "Quilt")]


def minecraft_releases() -> list[str]:
    vs = [v for v in mll_utils.get_version_list() if v.get("type") == "release"]
    return [v["id"] for v in sorted(vs, key=lambda v: v["releaseTime"], reverse=True)]


def loader_versions(loader: str, mc_version: str) -> list[str]:
    if loader == "vanilla":
        return []
    ml = mll_mod_loader.get_mod_loader(loader)
    if not ml.is_minecraft_version_supported(mc_version):
        return []
    return list(ml.get_loader_versions(mc_version, stable_only=True))


def create(lay: Layout, name: str, mc_version: str, loader: str, loader_version: str) -> LocalPack:
    existing = {p.id for p in localpacks.list_installed(lay)} | {d.name for d in lay.instances.iterdir()}
    lp = LocalPack(new_pack_id(name, existing), name, "0.0", mc_version, loader, loader_version)
    gd = localpacks.game_dir(lay, lp.id)
    for sub in ("mods", "config", "resourcepacks", "shaderpacks"):
        (gd / sub).mkdir(parents=True, exist_ok=True)
    localpacks.save(lay, lp)
    return lp
