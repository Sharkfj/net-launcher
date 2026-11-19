import json
import os
import time

from netlauncher import localpacks
from netlauncher.catalog import PackEntry
from netlauncher.localpacks import LocalPack


def test_save_and_list(home):
    gd = home.instances / "net"
    (gd / "mods").mkdir(parents=True)
    for n in ("a.jar", "b.jar", "c.jar.disabled"):
        (gd / "mods" / n).write_bytes(b"x")
    lp = LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", "Киберпанк", "play.example.net")
    localpacks.save(home, lp)
    [got] = localpacks.list_installed(home)
    assert got == lp and localpacks.mod_count(home, "net") == 2
    (home.instances / "junk").mkdir()
    assert [p.id for p in localpacks.list_installed(home)] == ["net"]


def test_from_entry_and_version_from_state(home):
    e = PackEntry("net", ".NET", "Киберпанк", "0.2", "1.21.1", "neoforge", "21.1.267", "u", "s", server="srv")
    localpacks.save(home, localpacks.from_entry(e))
    gd = home.instances / "net"
    (gd / ".net").mkdir(exist_ok=True)
    (gd / ".net" / "pack-state.json").write_text(json.dumps({"version": "0.3", "files": {}}))
    assert localpacks.get(home, "net").version == "0.3" and localpacks.get(home, "net").server == "srv"
    assert localpacks.get(home, "nope") is None


def test_newest_world(home):
    gd = home.instances / "net"
    for name, age in (("Старый", 100), ("Новый мир", 1)):
        (gd / "saves" / name).mkdir(parents=True)
        lvl = gd / "saves" / name / "level.dat"
        lvl.write_bytes(b"x")
        t = time.time() - age
        os.utime(lvl, (t, t))
    (gd / "saves" / "broken").mkdir()
    assert localpacks.newest_world(home, "net") == "Новый мир"
    assert localpacks.newest_world(home, "none") is None


def test_total_ram_positive():
    assert localpacks.total_ram_mb() > 512
