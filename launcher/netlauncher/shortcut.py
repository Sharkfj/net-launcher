"""Desktop shortcut for the launcher: a .desktop file on Linux, a .lnk on Windows."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NAME = ".NET Launcher"
ICON = Path(__file__).parent / "ui" / "assets" / "icon" / "icon.png"
SOURCE_ICON = Path(__file__).parent.parent / "packaging" / "icon.png"


def _windows() -> bool:
    return sys.platform.startswith("win")


def desktop_dir() -> Path:
    override = os.environ.get("NET_LAUNCHER_DESKTOP")
    if override:
        return Path(override)
    if _windows():
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                 "[Environment]::GetFolderPath('DesktopDirectory')"],
                capture_output=True, text=True, encoding="utf-8", check=True, timeout=5,
            ).stdout.strip()
            if out:
                return Path(out)
        except (OSError, subprocess.SubprocessError, UnicodeError):
            pass
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            return Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Desktop"


def launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    local = Path.home() / ".local" / "bin" / "net-launcher"
    if not _windows() and local.exists():
        return [str(local)]
    return [sys.executable, "-m", "netlauncher"]


def icon_path() -> Path:
    if _windows() and getattr(sys, "frozen", False):
        return Path(sys.executable)
    return ICON if ICON.exists() else SOURCE_ICON


def _exec_line(command: list[str]) -> str:
    return " ".join(f'"{c}"' if " " in c else c for c in command)


def _ps(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def create(command: list[str], icon: Path, name: str = NAME) -> Path:
    d = desktop_dir()
    d.mkdir(parents=True, exist_ok=True)
    if _windows():
        lnk = d / f"{name}.lnk"
        script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps(str(lnk))}); "
                  f"$s.TargetPath = {_ps(command[0])}; $s.Arguments = {_ps(subprocess.list2cmdline(command[1:]))}; "
                  f"$s.IconLocation = {_ps(str(icon) + ',0')}; $s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=30,
                       capture_output=True)
        return lnk
    f = d / "net-launcher.desktop"
    f.write_text("[Desktop Entry]\nType=Application\n"
                 f"Name={name}\nExec={_exec_line(command)}\nIcon={icon}\nTerminal=false\nCategories=Game;\n",
                 encoding="utf-8")
    f.chmod(0o755)
    try:
        subprocess.run(["gio", "set", str(f), "metadata::trusted", "true"], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass
    return f
