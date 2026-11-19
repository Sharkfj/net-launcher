"""Build the game command, run it, follow loading progress, explain crashes."""

from __future__ import annotations

import math
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import minecraft_launcher_lib.command as mll_command

from netlauncher import __version__
from netlauncher.auth_ely import Account
from netlauncher.gameinstall import InstalledGame


@dataclass
class LaunchSpec:
    game: InstalledGame
    mc_dir: Path
    game_dir: Path
    account: Account
    ram_mb: int
    fullscreen: bool
    width: int
    height: int
    authlib: Path
    world: str | None = None
    server: str | None = None


def build_command(spec: LaunchSpec) -> list[str]:
    jvm = [f"-Xmx{spec.ram_mb}m", f"-Xms{min(spec.ram_mb, 2048)}m", f"-javaagent:{spec.authlib}=ely.by",
           "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8"]
    options = {
        "username": spec.account.name, "uuid": spec.account.uuid, "token": spec.account.access_token,
        "executablePath": str(spec.game.java), "jvmArguments": jvm, "launcherName": "NETLauncher",
        "launcherVersion": __version__, "gameDirectory": str(spec.game_dir),
    }
    if not spec.fullscreen:
        options.update(customResolution=True, resolutionWidth=str(spec.width), resolutionHeight=str(spec.height))
    if spec.world:
        options["quickPlaySingleplayer"] = spec.world
    elif spec.server:
        options["quickPlayMultiplayer"] = spec.server
    return mll_command.get_minecraft_command(spec.game.version_id, str(spec.mc_dir), options)


def apply_fullscreen(game_dir: Path, on: bool) -> None:
    p = Path(game_dir) / "options.txt"
    value = f"fullscreen:{'true' if on else 'false'}"
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for i, line in enumerate(lines):
        if line.startswith("fullscreen:"):
            lines[i] = value
            break
    else:
        lines.append(value)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Stage(Enum):
    STARTING = "Запуск"
    LOADING = "Загрузка модов"
    RESOURCES = "Загрузка ресурсов"
    MENU = "Главное меню"
    WORLD = "Вход в мир"
    EXITED = "Игра закрыта"


MARKERS = [
    (Stage.STARTING, 0.03, ("ModLauncher running",)),
    (Stage.LOADING, 0.10, ("[modloading-worker",)),
    (Stage.RESOURCES, 0.70, ("Reloading ResourceManager",)),
    (Stage.MENU, 0.97, ("RealmsAvailability", "RealmsClient", "TitleScreen")),
    (Stage.WORLD, 0.99, ("Starting integrated minecraft server", "Connecting to ")),
    (Stage.EXITED, 1.00, ("Stopping!",)),
]
ORDER = [s for s, _, _ in MARKERS]
BASE = {s: f for s, f, _ in MARKERS}


class LogProgress:
    """Feed game log lines; get (stage, fraction) whenever progress moves forward."""

    def __init__(self):
        self.stage: Stage | None = None
        self.frac = 0.0
        self._lines_in_stage = 0
        self._sound = False

    def _advance(self, stage: Stage, frac: float):
        frac = min(max(frac, self.frac), 1.0)
        if stage is self.stage and frac - self.frac < 0.005:
            return None
        if stage is not self.stage:
            self._lines_in_stage = 0
        self.stage, self.frac = stage, frac
        return stage, frac

    def feed(self, line: str):
        for stage, frac, keys in reversed(MARKERS):
            if any(k in line for k in keys):
                if self.stage is None or ORDER.index(stage) > ORDER.index(self.stage):
                    return self._advance(stage, frac)
                break
        if "Sound engine started" in line and (self.stage is None
                                               or ORDER.index(self.stage) <= ORDER.index(Stage.RESOURCES)):
            self._sound = True
            return self._advance(Stage.RESOURCES, 0.88)
        if self.stage in (Stage.LOADING, Stage.RESOURCES):
            self._lines_in_stage += 1
            lo = BASE[self.stage]
            hi = 0.68 if self.stage is Stage.LOADING else 0.95
            target = lo + (hi - lo) * (1 - math.exp(-self._lines_in_stage / 400))
            return self._advance(self.stage, target)
        return None

    def idle(self, seconds: float):
        """No new log lines for `seconds`: after the sound engine is up that means the menu is shown."""
        if self.stage is Stage.RESOURCES and self._sound and seconds >= 3.0:
            return self._advance(Stage.MENU, BASE[Stage.MENU])
        return None


class GameProcess:
    def __init__(self, game_dir: Path):
        self.game_dir = Path(game_dir)
        self.log_path = self.game_dir / "logs" / "latest.log"
        self.proc: subprocess.Popen | None = None

    def start(self, cmd: list[str], cwd: Path) -> None:
        out_dir = self.game_dir / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = open(out_dir / "launcher-output.log", "wb")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=out, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, creationflags=flags)
        out.close()

    def poll(self) -> int | None:
        return None if self.proc is None else self.proc.poll()


@dataclass
class CrashInfo:
    description: str
    cause: str
    suspects: str
    report: Path


def crash_info(game_dir: Path, since: float) -> CrashInfo | None:
    d = Path(game_dir) / "crash-reports"
    if not d.is_dir():
        return None
    reports = [p for p in d.glob("*.txt") if p.stat().st_mtime >= since]
    if not reports:
        return None
    rep = max(reports, key=lambda p: p.stat().st_mtime)
    text = rep.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^Description:\s*(.+)$", text, re.M)
    description = m.group(1).strip() if m else ""
    cause = ""
    if m:
        for line in text[m.end():].splitlines():
            if line.strip():
                cause = line.strip()
                break
    s = re.search(r"Suspected Mods?:\s*\n((?:[ \t]+\S.*\n?)+)", text)
    suspects = ", ".join(x.strip() for x in s.group(1).splitlines() if x.strip()) if s else ""
    return CrashInfo(description, cause, suspects, rep)
