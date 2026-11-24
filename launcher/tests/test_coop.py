from pathlib import Path
from types import SimpleNamespace

from netlauncher import coop, localpacks
from netlauncher.localpacks import LocalPack
from netlauncher.modrinth import API
from netlauncher.pack import save_state
from netlauncher.ui.app import make_context
from tests.fakes import FakeHttp, sha1
from tests.jars import jar_bytes, toml_for


def test_coop_own_install_and_official_requires_supplied_file(home):
    pack = LocalPack("sky", "Sky", "1", "1.21.1", "neoforge", "21")
    gd = localpacks.game_dir(home, pack.id)
    localpacks.save(home, pack)
    data = jar_bytes(toml=toml_for("e4mc_minecraft", "e4mc"))
    url = "https://cdn.modrinth.com/e4mc.jar"
    release = {"project_id": coop.PROJECT, "id": "v", "files": [
        {"filename": "e4mc.jar", "url": url, "hashes": {"sha1": sha1(data)}}]}
    http = FakeHttp({f"{API}/project/{coop.PROJECT}/version": [release],
                     f"{API}/projects": [{"id": coop.PROJECT, "title": "e4mc"}]}, {url: data})
    ctx = make_context(home, http)
    assert coop.available(ctx, pack)
    assert http.calls[-1].params == {"game_versions": '["1.21.1"]', "loaders": '["neoforge"]'}
    coop.set_enabled(ctx, pack, True, None)
    assert (gd / "mods/e4mc.jar").read_bytes() == data and (gd / coop.OPT_IN).exists()
    coop.set_enabled(ctx, pack, False, None)
    assert not (gd / coop.OPT_IN).exists()
    pack.official = True
    http.calls.clear()
    assert not coop.available(ctx, pack)
    save_state(gd, {"files": {"mods/e4mc.jar": {"sha1": sha1(data)}}})
    assert coop.available(ctx, pack)
    coop.set_enabled(ctx, pack, True, None)
    assert not http.calls


def test_session_log_only_reads_new_lines_including_after_rotation(tmp_path):
    log = tmp_path / "latest.log"
    old = "[11:00:00] [Netty IO/INFO]: Domain assigned: old.na.e4mc.link\n"
    log.write_text(old)
    cursor = coop.SessionLog(log)
    assert cursor.lines() == []
    line = "[11:00:03] [Netty/INFO] [e4mc_minecraft/]: Domain assigned: nine-star.eu.e4mc.link"
    log.write_text(line)
    assert cursor.lines() == []
    with log.open("a") as f:
        f.write("\n")
    assert cursor.lines() == [line]
    assert coop.assigned_domain(line) == "nine-star.eu.e4mc.link"
    assert coop.assigned_domain(old.strip()) == "old.na.e4mc.link"
    assert not coop.assigned_domain(line + ".example.org")
    assert not coop.assigned_domain(line.replace("Domain assigned:", "[CHAT] Domain assigned:"))
    log.rename(tmp_path / "archived.log")
    log.write_text(old)
    assert cursor.lines() == [old.strip()]


def test_invites_carry_identity_and_match_shared_copy(home):
    events = []
    client = SimpleNamespace(presence=lambda *a, **k: {"friends": [{"name": "A"}, {"name": "B"}]},
                             invite=lambda *a, **k: events.append((a, k)))
    coop.invite_friends(client, "Sky", "s1", "2", "star.eu.e4mc.link")
    assert [args[0] for args, _ in events] == ["A", "B"]
    assert all(d == {"pack_id": "s1", "pack_version": "2"} for _, d in events)
    for pid, version in [("s1", "1"), ("mine", "2"), ("copy", "2")]:
        localpacks.save(home, LocalPack(pid, "Sky", version, "1.21.1", "fabric", "0.16"))
    (home.instances / "copy/.net/shared-id").write_text("s1")
    assert coop.invited_pack(home, "Sky", "s1", "2").id == "copy"
    assert coop.invited_pack(home, "Sky", "s1", "3") is None
