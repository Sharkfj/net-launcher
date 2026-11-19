"""Install Minecraft, the mod loader and Java via minecraft-launcher-lib; fetch authlib-injector."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib.install as mll_install
import minecraft_launcher_lib.mod_loader as mll_mod_loader
import minecraft_launcher_lib.runtime as mll_runtime

from netlauncher.net import HashMismatch, Http, HttpError, Offline
from netlauncher.paths import Layout

AUTHLIB_META = "https://authlib-injector.yushi.moe/artifact/latest.json"
MARKER = ".net-installed.json"
Progress = Callable[[str, int, int], None]


@dataclass
class InstalledGame:
    version_id: str
    java: Path


def _callbacks(progress: Progress) -> dict:
    state = {"status": "", "cur": 0, "max": 0}

    def status(s):
        state["status"] = str(s)
        progress(state["status"], state["cur"], state["max"])

    def cur(v):
        state["cur"] = int(v)
        progress(state["status"], state["cur"], state["max"])

    def mx(v):
        state["max"] = int(v)

    return {"setStatus": status, "setProgress": cur, "setMax": mx}


def _gui_java(java: Path) -> Path:
    if sys.platform == "win32":
        w = java.with_name("javaw.exe")
        if w.exists():
            return w
    return java


class GameInstaller:
    def __init__(self, lay: Layout, http: Http):
        self.lay, self.http = lay, http

    def _marker(self) -> dict:
        try:
            return json.loads((self.lay.minecraft / MARKER).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def ensure(self, mc_version: str, loader: str, loader_version: str, progress: Progress,
               force: bool = False) -> InstalledGame:
        key = f"{mc_version}|{loader}|{loader_version}"
        marks = self._marker()
        done = marks.get(key)
        if done and not force and Path(done["java"]).exists():
            return InstalledGame(done["version_id"], Path(done["java"]))
        mc = str(self.lay.minecraft)
        cb = _callbacks(progress)
        progress("Minecraft " + mc_version, 0, 0)
        mll_install.install_minecraft_version(mc_version, mc, callback=cb)
        info = mll_runtime.get_version_runtime_information(mc_version, mc) or {"name": "java-runtime-delta"}
        progress("Java", 0, 0)
        mll_runtime.install_jvm_runtime(info["name"], mc, callback=cb)
        java = Path(mll_runtime.get_executable_path(info["name"], mc))
        if loader and loader != "vanilla":
            progress(loader, 0, 0)
            version_id = mll_mod_loader.get_mod_loader(loader).install(
                mc_version, mc, loader_version=loader_version, callback=cb, java=str(java))
        else:
            version_id = mc_version
        java = _gui_java(java)
        marks[key] = {"version_id": version_id, "java": str(java)}
        (self.lay.minecraft / MARKER).write_text(json.dumps(marks, ensure_ascii=False), encoding="utf-8")
        return InstalledGame(version_id, java)

    def _cached_authlib(self) -> Path | None:
        jars = sorted(self.lay.cache.glob("authlib-injector-*.jar"), key=lambda p: p.stat().st_mtime)
        return jars[-1] if jars else None

    def ensure_authlib(self) -> Path:
        try:
            meta = self.http.get_json(AUTHLIB_META)
        except (Offline, HttpError):
            cached = self._cached_authlib()
            if cached is None:
                raise
            return cached
        dest = self.lay.cache / f"authlib-injector-{meta['version']}.jar"
        want = meta["checksums"]["sha256"].lower()
        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == want:
            return dest
        self.http.download(meta["download_url"], dest)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != want:
            dest.unlink(missing_ok=True)
            raise HashMismatch(dest)
        return dest
