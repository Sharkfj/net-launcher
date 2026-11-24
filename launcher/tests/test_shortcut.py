import os
import stat
import subprocess
from pathlib import Path

from netlauncher import shortcut


class Ran:
    def __init__(self, stdout=""):
        self.calls = []
        self.stdout = stdout

    def __call__(self, args, **kw):
        self.calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=self.stdout, stderr="")


def test_desktop_dir_honours_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NET_LAUNCHER_DESKTOP", str(tmp_path / "D"))
    assert shortcut.desktop_dir() == tmp_path / "D"


def test_desktop_dir_linux_xdg(monkeypatch):
    monkeypatch.delenv("NET_LAUNCHER_DESKTOP")
    monkeypatch.setattr(shortcut.sys, "platform", "linux")
    monkeypatch.setattr(shortcut.subprocess, "run", Ran("/home/x/Рабочий стол\n"))
    assert shortcut.desktop_dir() == Path("/home/x/Рабочий стол")


def test_linux_desktop_file(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "linux")
    ran = Ran()
    monkeypatch.setattr(shortcut.subprocess, "run", ran)
    f = shortcut.create(["/x/net-launcher"], Path("/x/icon.png"))
    text = f.read_text(encoding="utf-8")
    assert f == tmp_path / "Desktop" / "net-launcher.desktop"
    assert "Exec=/x/net-launcher" in text and "Icon=/x/icon.png" in text and "Name=.NET Launcher" in text
    assert f.stat().st_mode & stat.S_IXUSR
    assert ran.calls and ran.calls[0][:2] == ["gio", "set"]


def test_linux_exec_quotes_spaces(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "linux")
    monkeypatch.setattr(shortcut.subprocess, "run", Ran())
    f = shortcut.create(["/home/a b/net-launcher", "-m", "x"], Path("/i.png"))
    assert 'Exec="/home/a b/net-launcher" -m x' in f.read_text(encoding="utf-8")


def test_windows_shortcut_command(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "win32")
    ran = Ran()
    monkeypatch.setattr(shortcut.subprocess, "run", ran)
    lnk = shortcut.create([r"C:\Games\NET-Launcher.exe"], Path(r"C:\Games\NET-Launcher.exe"))
    assert lnk.name == ".NET Launcher.lnk"
    cmd = ran.calls[0]
    assert cmd[0] == "powershell" and "CreateShortcut" in cmd[-1] and ".NET Launcher.lnk" in cmd[-1]
    assert r"C:\Games\NET-Launcher.exe" in cmd[-1]
