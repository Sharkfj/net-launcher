from types import SimpleNamespace

import pytest

from netlauncher import chat_packs, localpacks
from netlauncher.curseforge import API
from netlauncher.net import HashMismatch, HttpError
from netlauncher.pack import add_manual
from tests.fakes import FakeHttp, sha1


@pytest.mark.parametrize("lookup_available", [False, True])
def test_curseforge_http_error_keeps_shared_pack_installable(home, tmp_path, lookup_available):
    modrinth_url = "https://cdn.modrinth.com/example.jar"
    curseforge_url = "https://edge.forgecdn.net/example.jar"
    lookup_url = f"{API}/mods/1755743/files/9612778"
    mr_data, cf_data = b"modrinth mod", b"curseforge mod"
    mr_hash, cf_hash = sha1(mr_data), sha1(cf_data)
    http = FakeHttp(downloads={modrinth_url: mr_data})
    if lookup_available:
        # The file metadata can be available even when the CDN denies the download.
        http.routes[lookup_url] = {
            "data": {"hashes": [{"algo": 1, "value": cf_hash}], "downloadUrl": curseforge_url}
        }
    else:
        http.routes[lookup_url] = HttpError(503, lookup_url)

    mr_file = SimpleNamespace(sha1=mr_hash, url=modrinth_url)
    ctx = SimpleNamespace(
        lay=home, catalog=None, http=http,
        settings=SimpleNamespace(curseforge_key="test-key"),
        modrinth=SimpleNamespace(versions_by_hash=lambda _: {mr_hash: SimpleNamespace(files=[mr_file])}),
    )
    card = {
        "name": "Shared pack", "id": "shared", "version": "1",
        "mc": "1.21.1", "loader": "fabric", "loader_version": "0.16.9",
        "files": [
            {"path": "mods/curseforge.jar", "sha1": cf_hash, "cf_project": 1755743, "cf_file": 9612778},
            {"path": "mods/modrinth.jar", "sha1": mr_hash},
        ],
        "settings": "eJyrrgUAAXUA+Q==",
    }

    pack, index, missing = chat_packs.install_card(ctx, card, lambda *_: None)
    directory = localpacks.game_dir(home, pack.id)
    assert (directory / "mods/modrinth.jar").read_bytes() == mr_data
    assert [(file.path, file.sha1) for file in missing] == [("mods/curseforge.jar", cf_hash)]
    local_file = tmp_path / "manual.jar"
    local_file.write_bytes(b"wrong file")
    with pytest.raises(HashMismatch):
        add_manual(index, directory, local_file)
    local_file.write_bytes(cf_data)
    add_manual(index, directory, local_file)
    assert (directory / "mods/curseforge.jar").read_bytes() == cf_data


def test_received_pack_can_restore_a_missing_file(home):
    data = b"shared mod"
    digest = sha1(data)
    url = "https://cdn.modrinth.com/example.jar"
    file = SimpleNamespace(url=url, sha1=digest, size=len(data))
    ctx = SimpleNamespace(
        lay=home, catalog=None, http=FakeHttp(downloads={url: data}),
        modrinth=SimpleNamespace(versions_by_hash=lambda _: {digest: SimpleNamespace(files=[file])}),
    )
    card = {
        "name": "Shared", "id": "shared", "version": "1", "mc": "1.21.1", "loader": "fabric",
        "loader_version": "0.16.9", "files": [{"path": "mods/example.jar", "sha1": digest}],
        "settings": "eJyrrgUAAXUA+Q==",
    }
    pack, _, missing = chat_packs.install_card(ctx, card, lambda *_: None)
    path = localpacks.game_dir(home, pack.id) / "mods/example.jar"
    assert not missing
    assert chat_packs.shared_files_to_repair(ctx, pack) is None
    path.unlink()
    repair = chat_packs.shared_files_to_repair(ctx, pack)
    assert repair["files"] == card["files"]
    _, _, missing = chat_packs.repair_shared_files(ctx, pack, repair, lambda *_: None)
    assert not missing and path.read_bytes() == data
