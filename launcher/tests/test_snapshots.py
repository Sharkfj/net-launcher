from netlauncher import snapshots


def _files(d):
    return sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())


def _game(tmp_path, name="game"):
    gd = tmp_path / name
    (gd / "mods").mkdir(parents=True)
    (gd / "mods" / "a.jar").write_bytes(b"a")
    (gd / "config").mkdir()
    (gd / "config" / "x.toml").write_text("v=1")
    return gd


def test_create_and_restore(tmp_path):
    gd, root = _game(tmp_path), tmp_path / "snaps"
    snap = snapshots.create(root, gd, "Установка: Particle Rain")
    assert snap.parts == ["mods", "config"] and snap.reason == "Установка: Particle Rain" and snap.size_bytes == 4
    before = _files(gd)
    (gd / "mods" / "a.jar").unlink()
    (gd / "mods" / "b.jar").write_bytes(b"b")
    (gd / "config" / "x.toml").write_text("v=2")
    snapshots.restore(root, snap, gd)
    assert _files(gd) == before and (gd / "config" / "x.toml").read_text() == "v=1"


def test_restore_makes_safety_snapshot(tmp_path):
    gd, root = _game(tmp_path), tmp_path / "snaps"
    snap = snapshots.create(root, gd, "первый")
    (gd / "mods" / "b.jar").write_bytes(b"b")
    safety = snapshots.restore(root, snap, gd)
    assert safety.reason == "Перед откатом" and (safety.path / "mods" / "b.jar").exists()
    assert [s.id for s in snapshots.list_snapshots(root)] == [safety.id, snap.id]


def test_list_ignores_junk_and_sorts_newest_first(tmp_path):
    gd, root = _game(tmp_path), tmp_path / "snaps"
    a = snapshots.create(root, gd, "a")
    b = snapshots.create(root, gd, "b")
    (root / "junk").mkdir()
    assert [s.id for s in snapshots.list_snapshots(root)] == [b.id, a.id]
    assert a.id != b.id


def test_delete(tmp_path):
    gd, root = _game(tmp_path), tmp_path / "snaps"
    s = snapshots.create(root, gd, "a")
    snapshots.delete(s)
    assert snapshots.list_snapshots(root) == []


def test_prune_keeps_newest(tmp_path):
    gd, root = _game(tmp_path), tmp_path / "snaps"
    made = [snapshots.create(root, gd, str(i)) for i in range(5)]
    snapshots.prune(root, keep=2)
    assert [s.id for s in snapshots.list_snapshots(root)] == [made[4].id, made[3].id]
    snapshots.prune(root, keep=0)
    assert [s.id for s in snapshots.list_snapshots(root)] == [made[4].id]


def test_snapshot_cyrillic_paths(tmp_path):
    gd = tmp_path / "Рабочий стол" / "игра"
    (gd / "mods").mkdir(parents=True)
    (gd / "mods" / "Мод (1).jar").write_bytes(b"m")
    root = tmp_path / "Снимки"
    s = snapshots.create(root, gd, "Удаление: Мод")
    (gd / "mods" / "Мод (1).jar").unlink()
    snapshots.restore(root, s, gd)
    assert (gd / "mods" / "Мод (1).jar").read_bytes() == b"m"


def test_empty_game_dir_snapshot_has_no_parts(tmp_path):
    gd = tmp_path / "empty"
    gd.mkdir()
    s = snapshots.create(tmp_path / "snaps", gd, "пусто")
    assert s.parts == [] and s.size_bytes == 0
