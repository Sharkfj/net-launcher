# PyInstaller spec: Windows → one NET-Launcher.exe, Linux → folder dist/net-launcher/
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
WIN = sys.platform == "win32"
datas = [(str(ROOT / "netlauncher" / "ui" / "assets"), "netlauncher/ui/assets")]
datas += collect_data_files("minecraft_launcher_lib")

a = Analysis([str(ROOT / "packaging" / "entry.py")], pathex=[str(ROOT)], datas=datas,
             hiddenimports=["PySide6.QtNetwork"],
             excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQuick", "PySide6.QtQml",
                       "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf"])
pyz = PYZ(a.pure)
icon = str(ROOT / "packaging" / ("icon.ico" if WIN else "icon.png"))
if WIN:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="NET-Launcher", console=False, icon=icon, upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="net-launcher", console=False, icon=icon)
    coll = COLLECT(exe, a.binaries, a.datas, name="net-launcher")
