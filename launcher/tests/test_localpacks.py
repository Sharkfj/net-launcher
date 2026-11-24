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


def test_localpack_official_flag(home):
    import json
    from netlauncher.catalog import PackEntry
    lp = localpacks.from_entry(PackEntry("net", ".NET", "", "0.1", "1.21.1", "neoforge", "21.1.267", "", ""))
    assert lp.official is True
    old = localpacks.LocalPack("old", "Old", "1", "1.21.1", "fabric", "0.16")
    localpacks.save(home, old)
    f = localpacks.game_dir(home, "old") / ".net" / "pack.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    data.pop("official", None)
    f.write_text(json.dumps(data), encoding="utf-8")
    assert localpacks.get(home, "old").official is False


def _world(home, pack_id, name="World"):
    w = localpacks.game_dir(home, pack_id) / "saves" / name
    w.mkdir(parents=True)
    (w / "level.dat").write_bytes(b"x")
    return w


def test_delete_keeps_worlds(home):
    localpacks.save(home, localpacks.LocalPack("p1", "P1", "1", "1.21.1", "fabric", "0.16"))
    _world(home, "p1")
    kept = localpacks.delete(home, "p1", keep_worlds=True)
    assert not localpacks.game_dir(home, "p1").exists()
    assert kept is not None and (kept / "World" / "level.dat").exists()
    assert kept.parent == home.backups / "p1"


def test_delete_without_worlds(home):
    localpacks.save(home, localpacks.LocalPack("p2", "P2", "1", "1.21.1", "fabric", "0.16"))
    _world(home, "p2")
    assert localpacks.delete(home, "p2", keep_worlds=False) is None
    assert not localpacks.game_dir(home, "p2").exists()


def test_locked_rules():
    from netlauncher.catalog import Catalog
    from netlauncher.settings import Settings
    cat = Catalog("0.2.2", {}, [PackEntry("net", ".NET", "", "0.1", "1.21.1", "neoforge", "21.1.267", "", "")])
    player, author = Settings(), Settings(author_mode=True, github_token="t")
    official = localpacks.LocalPack("x", "X", "1", "1.21.1", "neoforge", "1", official=True)
    listed = localpacks.LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267")
    own = localpacks.LocalPack("mine", "Mine", "", "1.21.1", "fabric", "0.16")
    assert localpacks.locked(official, player, None) and localpacks.locked(listed, player, cat)
    assert not localpacks.locked(official, author, cat) and not localpacks.locked(listed, author, cat)
    assert not localpacks.locked(own, player, cat)
