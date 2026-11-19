import json
import zipfile

import pytest

from netlauncher import snapshots
from netlauncher.net import HashMismatch
from netlauncher.pack import (ManualFile, MrPack, PackFile, PackIndex, UnsafePath, add_manual, apply_update,
                              load_state, plan_update, write_mrpack)
from tests.fakes import FakeHttp, sha1, sha512

A1, A2, B1, FOG1, FOG2, CHROME = b"a-v1", b"a-v2", b"b-v1", b"fog-v1", b"fog-v2", b"chromeware"


def pf(path, data, project, client="required", server="required"):
    return PackFile(path, sha1(data), sha512(data), len(data),
                    [f"https://cdn.modrinth.com/data/{project}/versions/x/{path.split('/')[-1]}"], client, server)


def make_pack(tmp_path, version, files, overrides=None, manual=(), preserve=(), name=None):
    root = tmp_path / f"src-{version}"
    root.mkdir(exist_ok=True)
    for rel, data in (overrides or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    idx = PackIndex(".NET", version, "1.21.1", "neoforge", "21.1.267", list(files), list(manual), list(preserve),
                    f"Версия {version}")
    path = write_mrpack(tmp_path / (name or f"net-{version}.mrpack"), idx, root, sorted((overrides or {}).keys()))
    return MrPack.open(path)


def serve(files_data):
    http = FakeHttp()
    for f, data in files_data:
        http.downloads[f.urls[0]] = data
    return http


def install(tmp_path, pack, gd, http):
    plan = plan_update(pack, gd, load_state(gd))
    return plan, apply_update(plan, pack, gd, http, tmp_path / "cache", tmp_path / "snaps")


def test_roundtrip_mrpack(tmp_path):
    a = pf("mods/a.jar", A1, "pa")
    p = make_pack(tmp_path, "0.1", [a], {"config/x.toml": b"x=1"},
                  manual=[ManualFile("mods/chromeware.jar", sha1(CHROME), "Create: Chromeware", "https://cf/x")],
                  preserve=["config/xaero"])
    assert p.index.version == "0.1" and p.index.files == [a] and p.index.loader_version == "21.1.267"
    assert p.index.manual[0].name == "Create: Chromeware" and p.index.preserve == ["config/xaero"]
    assert p.override_paths() == ["config/x.toml"] and p.read_override("config/x.toml") == b"x=1"
    with zipfile.ZipFile(p.path) as z:
        idx = json.loads(z.read("modrinth.index.json"))
    assert idx["formatVersion"] == 1 and idx["dependencies"] == {"minecraft": "1.21.1", "neoforge": "21.1.267"}
    assert idx["files"][0]["env"] == {"client": "required", "server": "required"}


@pytest.mark.parametrize("bad", ["../../evil.jar", "/etc/passwd", "C:/Windows/x.dll", "mods/../../x.jar"])
def test_rejects_zip_slip(tmp_path, bad):
    path = tmp_path / "evil.mrpack"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("modrinth.index.json", json.dumps({
            "formatVersion": 1, "game": "minecraft", "versionId": "1", "name": "x",
            "dependencies": {"minecraft": "1.21.1", "neoforge": "1"},
            "files": [{"path": bad, "hashes": {"sha1": "0", "sha512": "0"}, "downloads": ["https://x"],
                       "fileSize": 1}]}))
    with pytest.raises(UnsafePath):
        MrPack.open(path)


def test_rejects_override_slip(tmp_path):
    path = tmp_path / "evil.mrpack"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("modrinth.index.json", json.dumps({"formatVersion": 1, "game": "minecraft", "versionId": "1",
                                                      "name": "x", "dependencies": {"minecraft": "1.21.1"},
                                                      "files": []}))
        z.writestr("overrides/../../evil.sh", "x")
    with pytest.raises(UnsafePath):
        MrPack.open(path)


def test_fresh_install_plan(tmp_path):
    a = pf("mods/a.jar", A1, "pa")
    srv = pf("mods/server-only.jar", B1, "ps", client="unsupported")
    p = make_pack(tmp_path, "0.1", [a, srv], {"config/x.toml": b"x=1", "options.txt": b"lang:ru_ru"})
    gd = tmp_path / "игра"
    plan, state = install(tmp_path, p, gd, serve([(a, A1)]))
    assert plan.downloads == [a] and sorted(plan.overrides) == ["config/x.toml", "options.txt"]
    assert (gd / "mods/a.jar").read_bytes() == A1 and not (gd / "mods/server-only.jar").exists()
    assert state["version"] == "0.1" and load_state(gd)["files"]["mods/a.jar"]["sha1"] == sha1(A1)
    assert load_state(gd)["files"]["config/x.toml"]["server"] == "required"


def test_update_only_changed(tmp_path):
    a1, b = pf("mods/a-1.jar", A1, "pa"), pf("mods/b.jar", B1, "pb")
    gd = tmp_path / "игра"
    install(tmp_path, make_pack(tmp_path, "0.1", [a1, b]), gd, serve([(a1, A1), (b, B1)]))
    a2 = pf("mods/a-2.jar", A2, "pa")
    p2 = make_pack(tmp_path, "0.2", [a2])
    http = serve([(a2, A2)])
    plan, _ = install(tmp_path, p2, gd, http)
    assert plan.downloads == [a2] and sorted(plan.remove) == ["mods/a-1.jar", "mods/b.jar"]
    assert sorted(p.name for p in (gd / "mods").iterdir()) == ["a-2.jar"]
    assert [c.url for c in http.calls] == [a2.urls[0]]
    assert snapshots.list_snapshots(tmp_path / "snaps")[0].reason == "Перед обновлением сборки до 0.2"


def test_update_preserves_player_state(tmp_path):
    a, fog1 = pf("mods/a.jar", A1, "pa"), pf("mods/fog-1.jar", FOG1, "pfog", server="unsupported")
    p1 = make_pack(tmp_path, "0.1", [a, fog1], {"options.txt": b"lang:ru_ru", "config/x.toml": b"x=1"})
    gd = tmp_path / "игра"
    install(tmp_path, p1, gd, serve([(a, A1), (fog1, FOG1)]))
    (gd / "mods/my.jar").write_bytes(b"mine")
    (gd / "mods/fog-1.jar").rename(gd / "mods/fog-1.jar.disabled")
    (gd / "options.txt").write_text("lang:ru_ru\nmine")
    (gd / "saves/Мир").mkdir(parents=True)
    (gd / "saves/Мир/level.dat").write_bytes(b"world")
    fog2 = pf("mods/fog-2.jar", FOG2, "pfog", server="unsupported")
    p2 = make_pack(tmp_path, "0.2", [a, fog2], {"options.txt": b"lang:en_us", "config/x.toml": b"x=2",
                                                "saves/Мир/level.dat": b"evil"})
    plan, _ = install(tmp_path, p2, gd, serve([(fog2, FOG2)]))
    assert (gd / "mods/my.jar").exists() and (gd / "mods/fog-2.jar.disabled").exists()
    assert not (gd / "mods/fog-2.jar").exists() and not (gd / "mods/fog-1.jar.disabled").exists()
    assert (gd / "options.txt").read_text() == "lang:ru_ru\nmine" and (gd / "saves/Мир/level.dat").read_bytes() == b"world"
    assert (gd / "config/x.toml").read_bytes() == b"x=2"


def test_preserve_only_if_missing(tmp_path):
    gd = tmp_path / "игра"
    p1 = make_pack(tmp_path, "0.1", [], {"config/xaero/minimap.txt": b"pack"}, preserve=["config/xaero"])
    install(tmp_path, p1, gd, FakeHttp())
    (gd / "config/xaero/minimap.txt").write_bytes(b"player")
    p2 = make_pack(tmp_path, "0.2", [], {"config/xaero/minimap.txt": b"pack2"}, preserve=["config/xaero"])
    install(tmp_path, p2, gd, FakeHttp())
    assert (gd / "config/xaero/minimap.txt").read_bytes() == b"player"


def test_apply_update_failure_keeps_old_state(tmp_path):
    a = pf("mods/a.jar", A1, "pa")
    gd = tmp_path / "игра"
    install(tmp_path, make_pack(tmp_path, "0.1", [a]), gd, serve([(a, A1)]))
    b, c = pf("mods/b.jar", B1, "pb"), pf("mods/c.jar", A2, "pc")
    p2 = make_pack(tmp_path, "0.2", [b, c], {"config/new.toml": b"n"})
    http = serve([(b, B1), (c, b"corrupted")])
    with pytest.raises(HashMismatch):
        install(tmp_path, p2, gd, http)
    assert load_state(gd)["version"] == "0.1"
    assert sorted(p.name for p in (gd / "mods").iterdir()) == ["a.jar"] and not (gd / "config/new.toml").exists()
    assert not list(gd.rglob("*.part")) and not list((tmp_path / "cache").rglob("*.part"))
    install(tmp_path, p2, gd, serve([(b, B1), (c, A2)]))
    assert load_state(gd)["version"] == "0.2"


def test_manual_missing_and_add(tmp_path):
    m = ManualFile("mods/chromeware-1.3.0.jar", sha1(CHROME), "Create: Chromeware", "https://cf/chromeware")
    gd = tmp_path / "игра"
    p = make_pack(tmp_path, "0.1", [], manual=[m])
    plan, _ = install(tmp_path, p, gd, FakeHttp())
    assert plan.manual_missing == [m]
    wrong = tmp_path / "Загрузки" / "other.jar"
    wrong.parent.mkdir()
    wrong.write_bytes(b"nope")
    with pytest.raises(HashMismatch):
        add_manual(p.index, gd, wrong)
    right = tmp_path / "Загрузки" / "chromeware (1).jar"
    right.write_bytes(CHROME)
    assert add_manual(p.index, gd, right) == m and (gd / m.path).read_bytes() == CHROME
    assert plan_update(p, gd, load_state(gd)).manual_missing == []
