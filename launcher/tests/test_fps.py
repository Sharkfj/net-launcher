from types import SimpleNamespace
from netlauncher import fps
from netlauncher.localpacks import LocalPack


def test_fps_restore_keeps_user_edits(tmp_path):
    options = tmp_path / "options.txt"
    options.write_text("renderDistance:16\nmusic:0\n")
    saved = fps.tune_options(tmp_path)
    assert "renderDistance:10" in options.read_text() and "music:0" in options.read_text()
    options.write_text(options.read_text().replace("simulationDistance:8", "simulationDistance:6"))
    lp = LocalPack("x", "X", "0", "1.21", "fabric", "1", fps=True, fps_options=saved)
    fps.disable(SimpleNamespace(game_dir=tmp_path), lp)
    assert options.read_text().splitlines() == ["renderDistance:16", "music:0", "simulationDistance:6"]


def test_mods_match_loader():
    assert "lithium" in fps.MODS["fabric"] and "embeddium" in fps.MODS["forge"]
    assert "lithium" not in fps.MODS["neoforge"] and "sodium" not in fps.MODS["forge"]


def test_disable_removes_only_installed_fps_mods(tmp_path):
    from netlauncher.library import NotAvailable
    lp = LocalPack("test", "Test", "1", "1.21", "fabric", "1")
    folder = tmp_path / "mods"
    folder.mkdir()
    (folder / "lithium.jar").write_bytes(b"existing")
    def plan_install(pid, _kind):
        if pid not in {"sodium", "lithium"}:
            raise NotAvailable(pid)
        file = SimpleNamespace(filename=pid + ".jar")
        return SimpleNamespace(items=[(pid, SimpleNamespace(primary_file=file))])
    def install(plan, kind, progress):
        for _, version in plan.items:
            (folder / version.primary_file.filename).write_bytes(b"installed")
    library = SimpleNamespace(game_dir=tmp_path, mr=SimpleNamespace(project=lambda slug: SimpleNamespace(id=slug)),
                              plan_install=plan_install, install=install)
    assert fps.enable(library, lp, None) == ["sodium.jar"]
    assert lp.fps and (folder / "lithium.jar").read_bytes() == b"existing"
    fps.disable(library, lp)
    assert not lp.fps and not (folder / "sodium.jar").exists()
    assert (folder / "lithium.jar").read_bytes() == b"existing"
