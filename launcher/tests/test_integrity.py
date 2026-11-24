import shutil

import pytest

from netlauncher import integrity, localpacks
from netlauncher.localpacks import LocalPack
from netlauncher.net import Offline
from netlauncher.pack import load_state
from tests.fakes import FakeHttp
from tests.test_pack import A1, B1, install, make_pack, pf, serve

SHADER = b"shader-zip"


@pytest.fixture
def installed(home, tmp_path):
    """An official pack 'net' 0.1 installed, with its .mrpack in the launcher cache."""
    a, b = pf("mods/a.jar", A1, "pa"), pf("mods/b.jar", B1, "pb")
    s = pf("shaderpacks/glow.zip", SHADER, "ps")
    pack = make_pack(tmp_path, "0.1", [a, b, s])
    gd = localpacks.game_dir(home, "net")
    http = serve([(a, A1), (b, B1), (s, SHADER)])
    install(tmp_path, pack, gd, http)
    (home.cache / "packs").mkdir(parents=True, exist_ok=True)
    shutil.copy(pack.path, home.cache / "packs" / "net-0.1.mrpack")
    lp = LocalPack("net", ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", official=True)
    localpacks.save(home, lp)
    return gd, lp, http


def test_check_clean_pack(installed):
    gd, lp, http = installed
    r = integrity.check(gd, load_state(gd))
    assert r.ok and (r.missing, r.changed, r.extra) == ([], [], [])


def test_check_finds_missing_changed_extra(installed):
    gd, lp, http = installed
    (gd / "mods" / "a.jar").unlink()
    (gd / "mods" / "b.jar").write_bytes(b"tampered")
    (gd / "mods" / "cheat.jar").write_bytes(b"x")
    (gd / "resourcepacks" / "xray").mkdir(parents=True)
    (gd / "resourcepacks" / "xray" / "pack.mcmeta").write_text("{}")
    r = integrity.check(gd, load_state(gd))
    assert r.missing == ["mods/a.jar"] and r.changed == ["mods/b.jar"]
    assert r.extra == ["mods/cheat.jar", "resourcepacks/xray"]


def test_shader_settings_ignored(installed):
    gd, lp, http = installed
    (gd / "shaderpacks" / "glow.zip.txt").write_text("bloom=0.5")
    (gd / "mods" / ".connector").mkdir()
    (gd / "mods" / ".connector" / "cache.bin").write_bytes(b"c")
    assert integrity.check(gd, load_state(gd)).ok


def test_check_uses_hash_cache(installed, monkeypatch):
    gd, lp, http = installed
    integrity.check(gd, load_state(gd))
    calls = []
    monkeypatch.setattr(integrity, "sha1_file", lambda p: calls.append(p) or "x")
    assert integrity.check(gd, load_state(gd)).ok and calls == []


def test_repair_moves_extra_mod(installed, home):
    gd, lp, http = installed
    (gd / "mods" / "cheat.jar").write_bytes(b"x")
    left = integrity.repair(integrity.check(gd, load_state(gd)), home, lp, http, lambda *a: None)
    assert left.ok and not (gd / "mods" / "cheat.jar").exists()
    moved = list((gd / ".net" / "removed").glob("*/mods/cheat.jar"))
    assert len(moved) == 1 and moved[0].read_bytes() == b"x"


def test_repair_restores_from_cached_mrpack(installed, home):
    gd, lp, http = installed
    (gd / "mods" / "a.jar").unlink()
    (gd / "mods" / "b.jar").write_bytes(b"tampered")
    left = integrity.repair(integrity.check(gd, load_state(gd)), home, lp, http, lambda *a: None)
    assert left.ok
    assert (gd / "mods" / "a.jar").read_bytes() == A1 and (gd / "mods" / "b.jar").read_bytes() == B1


def test_repair_offline_without_cache_raises(installed, home):
    gd, lp, http = installed
    (home.cache / "packs" / "net-0.1.mrpack").unlink()
    (gd / "mods" / "a.jar").unlink()
    report = integrity.check(gd, load_state(gd))
    with pytest.raises(Offline):
        integrity.repair(report, home, lp, FakeHttp(offline=True), lambda *a: None, mrpack_url="https://x/net.mrpack")
    with pytest.raises(integrity.NoPackFile):
        integrity.repair(report, home, lp, http, lambda *a: None)
