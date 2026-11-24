import zipfile

from netlauncher import localpacks, worlds


def _world(gd, name="Мир", data=b"v1"):
    w = gd / "saves" / name
    (w / "region").mkdir(parents=True, exist_ok=True)
    (w / "level.dat").write_bytes(data)
    (w / "region" / "r.0.0.mca").write_bytes(data * 10)
    return w


def test_list_worlds(home):
    gd = localpacks.game_dir(home, "p")
    _world(gd, "A")
    _world(gd, "B")
    (gd / "saves" / "junk").mkdir()  # no level.dat: not a world
    ws = worlds.list_worlds(gd)
    assert sorted(w.name for w in ws) == ["A", "B"]
    assert all(w.size > 0 and w.last_played > 0 for w in ws)
    assert worlds.list_worlds(localpacks.game_dir(home, "none")) == []


def test_backup_keeps_five(home):
    gd = localpacks.game_dir(home, "p")
    _world(gd)
    w = worlds.list_worlds(gd)[0]
    made = [worlds.backup(home, "p", w) for _ in range(7)]
    kept = worlds.backups(home, "p", "Мир")
    assert len(kept) == 5 and kept == sorted(made[-5:], reverse=True)
    assert all(p.parent == home.backups / "p" / "Мир" for p in kept)
    with zipfile.ZipFile(kept[0]) as z:
        assert sorted(z.namelist()) == ["level.dat", "region/r.0.0.mca"]


def test_restore_backs_up_current_first(home):
    gd = localpacks.game_dir(home, "p")
    _world(gd, data=b"old")
    saved = worlds.backup(home, "p", worlds.list_worlds(gd)[0])
    _world(gd, data=b"new")
    path = worlds.restore(home, "p", gd, saved)
    assert (path / "level.dat").read_bytes() == b"old"
    latest = worlds.backups(home, "p", "Мир")[0]
    with zipfile.ZipFile(latest) as z:
        assert z.read("level.dat") == b"new"


def test_restore_rejects_unsafe_zip(home, tmp_path):
    import pytest
    gd = localpacks.game_dir(home, "p")
    bad = home.backups / "p" / "Мир" / "evil.zip"
    bad.parent.mkdir(parents=True)
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../../escape.txt", "x")
    with pytest.raises(ValueError):
        worlds.restore(home, "p", gd, bad)
    assert not (gd.parent / "escape.txt").exists()


def test_backup_all(home):
    gd = localpacks.game_dir(home, "p")
    _world(gd, "A")
    _world(gd, "B")
    made = worlds.backup_all(home, "p", gd)
    assert len(made) == 2 and all(p.exists() for p in made)
