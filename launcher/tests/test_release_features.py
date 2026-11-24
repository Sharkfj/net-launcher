import hashlib

import pytest

from netlauncher import localpacks, updater
from netlauncher.launch import shareable_crash_details
from netlauncher.net import HashMismatch
from tests.fakes import FakeHttp


def test_find_update_uses_matching_published_installer():
    def release(version, name, *, draft=False):
        tag = "launcher-v" + version
        url = f"https://github.com/{updater.PACK_REPO}/releases/download/{tag}/{name}"
        return {"tag_name": tag, "draft": draft, "assets": [
            {"name": name, "state": "uploaded", "browser_download_url": url,
             "digest": "sha256:" + "a" * 64, "size": 100},
        ]}

    win, linux = "NET-Launcher-Setup.exe", "NET-Launcher-Linux-Setup.sh"
    http = FakeHttp({updater.RELEASES: [release("0.9.0", linux, draft=True), release("0.4.0", win),
                                      release("0.3.6-beta.1", linux), release("0.3.5", linux)]})
    assert updater.find_update(http, "0.3.5", system="linux", machine="x86_64").tag == "launcher-v0.3.6-beta.1"
    assert updater.find_update(http, "0.3.5", system="win32", machine="AMD64").name == win
    assert updater.find_update(http, "0.3.6", system="linux", machine="x86_64") is None


def test_updater_checks_the_asset_digest(tmp_path, monkeypatch):
    payload = b"installer"
    release = updater.Update("launcher-v0.3.6", "setup.sh", "https://example.test/setup",
                             hashlib.sha256(payload).hexdigest(), len(payload))
    monkeypatch.setattr(updater, "find_update", lambda *_: release)
    http = FakeHttp(downloads={release.url: b"untrusted"})
    with pytest.raises(HashMismatch):
        updater.download_update(http, tmp_path, "0.3.5", lambda *_: None)
    http.downloads[release.url] = payload
    assert updater.download_update(http, tmp_path, "0.3.5", lambda *_: None).read_bytes() == payload


@pytest.mark.parametrize("worlds", [False, True])
def test_copy_creates_an_independent_pack(home, worlds):
    source = localpacks.LocalPack("original", "Original", "1", "1.21.1", "fabric", "0.16.0",
                                  official=True, server="server.example")
    localpacks.save(home, source)
    original = localpacks.game_dir(home, source.id)
    (original / "mods").mkdir()
    (original / "mods/example.jar").write_bytes(b"mod")
    (original / "saves/world").mkdir(parents=True)
    (original / "saves/world/level.dat").write_bytes(b"world")
    (original / ".net/shared-id").write_text("anything")
    pack = localpacks.test_copy(home, source, "Test", worlds)
    dest = localpacks.game_dir(home, pack.id)
    assert not pack.official and not pack.server and pack.id != source.id
    assert (dest / "saves/world/level.dat").exists() is worlds
    assert not (dest / ".net/shared-id").exists()
    (dest / "mods/example.jar").write_bytes(b"changed")
    assert (original / "mods/example.jar").read_bytes() == b"mod"


def test_crash_report_excludes_exception_arguments(tmp_path):
    log = tmp_path / "latest.log"
    log.write_text('[Server thread/ERROR]: java.io.IOException: /home/user/private token=secret\n'
                   'Caused by: java.lang.Error: another secret\n')
    assert shareable_crash_details(log) == ["java.io.IOException", "java.lang.Error"]


def test_join_resumes_only_after_the_matching_pack_is_installed(home):
    from types import SimpleNamespace

    from netlauncher.auth_ely import offline_account
    from netlauncher.ui.pages.friends_page import FriendsPage

    account = offline_account("Player")
    joined = []
    ctx = SimpleNamespace(lay=home, accounts=SimpleNamespace(load=lambda: account))
    page = SimpleNamespace(ctx=ctx, _launch_join=lambda *args: joined.append(args))
    FriendsPage._remember_join(page, "Shared", "world.example", "Friend", "origin", "1",)
    old = localpacks.LocalPack("wrong", "Shared", "0", "1.21.1", "fabric", "0.16.0")
    localpacks.save(home, old)
    FriendsPage.resume_join(page, old.id)
    assert not joined
    pack = localpacks.LocalPack("copy", "Shared", "1", "1.21.1", "fabric", "0.16.0")
    localpacks.save(home, pack)
    (localpacks.game_dir(home, pack.id) / ".net/shared-id").write_text("origin")
    FriendsPage.resume_join(page, pack.id)
    assert joined == [(pack, "world.example", "Friend")]
    assert page.pending_join is None
