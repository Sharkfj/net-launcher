import base64
import json

import pytest

from netlauncher import author, catalog, importer
from netlauncher.catalog import Catalog, PackEntry
from netlauncher.modrinth import API, Modrinth
from netlauncher.net import HttpError
from netlauncher.pack import MrPack, PackIndex, PackFile
from tests.fakes import FakeHttp, sha1, sha512
from tests.jars import jar_bytes, toml_for

REPO = "user/net-pack"
CONTENTS = f"https://api.github.com/repos/{REPO}/contents/catalog.json"


def entry(pid="net", version="0.1", **kw):
    base = dict(id=pid, name=".NET", description="Киберпанк", version=version, mc_version="1.21.1",
                loader="neoforge", loader_version="21.1.267", mrpack_url="https://x/net.mrpack", mrpack_sha1="s",
                changelog="Первая версия")
    base.update(kw)
    return PackEntry(**base)


def test_is_newer():
    assert catalog.is_newer("0.10", "0.9") and catalog.is_newer("1.0.1", "1.0") and not catalog.is_newer("0.2", "0.2")
    assert not catalog.is_newer("0.1", "0.2")


def test_fetch_and_offline():
    data = {"format": 1, "launcher": {"version": "0.2.0", "urls": {"windows": "https://w"}},
            "packs": [vars(entry(server="play.example.net"))]}
    http = FakeHttp({CONTENTS: data})
    cat = catalog.fetch(http, REPO)
    assert cat.launcher_version == "0.2.0" and cat.get("net").server == "play.example.net" and cat.get("x") is None
    assert http.calls[-1].headers["Accept"] == "application/vnd.github.raw+json"
    assert catalog.fetch(FakeHttp(offline=True), REPO) is None
    assert catalog.fetch(FakeHttp(), REPO) is None


def test_env_override_local_file(tmp_path, monkeypatch):
    f = tmp_path / "Каталог.json"
    f.write_text(json.dumps({"format": 1, "packs": [vars(entry())]}), encoding="utf-8")
    monkeypatch.setenv("NET_LAUNCHER_CATALOG", str(f))
    assert catalog.resolve(FakeHttp()).get("net").version == "0.1"
    monkeypatch.delenv("NET_LAUNCHER_CATALOG")
    monkeypatch.setattr(catalog, "PACK_REPO", "")
    assert catalog.resolve(FakeHttp()) is None


def test_updates_map():
    cat = Catalog("0.1.0", {}, [entry("net", "0.3"), entry("other", "1.0")])
    assert set(catalog.updates(cat, {"net": "0.2", "other": "1.0"})) == {"net"}
    assert catalog.updates(None, {"net": "0.2"}) == {}


def _mr_world(gd):
    on_mr = jar_bytes(toml=toml_for("sodium", "Sodium"))
    mit = jar_bytes(toml=toml_for("cinematic", "Cinematic Interaction", license="MIT"))
    arr = jar_bytes(toml=toml_for("chromeware", "Create: Chromeware", license="All Rights Reserved",
                                  url="https://www.curseforge.com/minecraft/mc-mods/chromeware"))
    (gd / "mods").mkdir(parents=True)
    (gd / "mods" / "sodium.jar").write_bytes(on_mr)
    (gd / "mods" / "cinematic.jar").write_bytes(mit)
    (gd / "mods" / "chromeware-1.3.0.jar").write_bytes(arr)
    (gd / "mods" / "off.jar.disabled").write_bytes(b"x")
    (gd / "config").mkdir()
    (gd / "config" / "iris.properties").write_text("shaderPack=x")
    (gd / "options.txt").write_text("lang:ru_ru")
    (gd / "logs").mkdir()
    (gd / "logs" / "latest.log").write_text("no")
    ver = {"id": "v1", "project_id": "AANobbMI", "version_number": "0.8", "version_type": "release",
           "game_versions": ["1.21.1"], "loaders": ["neoforge"], "date_published": "2026-01-01", "dependencies": [],
           "files": [{"url": "https://cdn.modrinth.com/data/AANobbMI/versions/v1/sodium.jar", "filename": "sodium.jar",
                      "primary": True, "size": len(on_mr), "hashes": {"sha1": sha1(on_mr), "sha512": sha512(on_mr)}}]}
    http = FakeHttp({f"{API}/version_files": lambda c: {sha1(on_mr): ver} if sha1(on_mr) in c.body["hashes"] else {},
                     f"{API}/projects": [{"id": "AANobbMI", "slug": "sodium", "title": "Sodium", "description": "",
                                          "downloads": 1, "icon_url": "", "project_type": "mod",
                                          "client_side": "required", "server_side": "unsupported"}]})
    return Modrinth(http), on_mr


def test_build_classifies_mods(tmp_path):
    gd = tmp_path / "сборка"
    mr, on_mr = _mr_world(gd)
    res = author.build(gd, mr, ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", "Первая", None)
    [f] = res.index.files
    assert f.path == "mods/sodium.jar" and f.server == "unsupported" and f.client == "required"
    assert f.urls == ["https://cdn.modrinth.com/data/AANobbMI/versions/v1/sodium.jar"]
    assert "mods/cinematic.jar" in res.overrides and "config/iris.properties" in res.overrides
    assert "options.txt" in res.overrides and not any(o.startswith("logs/") for o in res.overrides)
    assert not any("off.jar" in o for o in res.overrides)
    [m] = res.index.manual
    assert m.path == "mods/chromeware-1.3.0.jar" and m.page_url.startswith("https://www.curseforge.com")
    assert res.warnings == ["Create: Chromeware: закрытая лицензия, игроки скачают вручную"]
    p = author.write(res, gd, tmp_path / "out", "net")
    assert p.name == "net-0.1.mrpack" and MrPack.open(p).read_override("mods/cinematic.jar")


def test_build_diff(tmp_path):
    gd = tmp_path / "сборка"
    mr, _ = _mr_world(gd)
    prev = PackIndex(".NET", "0.1", "1.21.1", "neoforge", "21.1.267",
                     [PackFile("mods/sodium-old.jar", "a", "b", 1,
                               ["https://cdn.modrinth.com/data/AANobbMI/versions/v0/sodium-old.jar"]),
                      PackFile("mods/gone.jar", "c", "d", 1, ["https://cdn.modrinth.com/data/GONE/versions/v/gone.jar"])])
    res = author.build(gd, mr, ".NET", "0.2", "1.21.1", "neoforge", "21.1.267", "", prev)
    assert res.diff.updated == ["sodium.jar"] and res.diff.removed == ["gone.jar"]
    assert "cinematic.jar" in res.diff.added and "chromeware-1.3.0.jar" in res.diff.added


def _gh(existing):
    put = {}

    def contents(call):
        if existing is None:
            return HttpError(404, CONTENTS)
        raw = json.dumps(existing).encode()
        return {"sha": "abc", "content": base64.b64encode(raw).decode()}

    def put_contents(call):
        put["body"] = json.loads(call.body)
        return {"content": {}}

    http = FakeHttp({
        f"https://api.github.com/repos/{REPO}/releases": {"id": 7, "html_url": "https://github.com/r/7",
                                                          "upload_url": "x"},
        f"https://uploads.github.com/repos/{REPO}/releases/7/assets?name=net-0.2.mrpack":
            {"browser_download_url": "https://github.com/dl/net-0.2.mrpack"},
        CONTENTS: contents,
    })
    http.routes[("PUT", CONTENTS)] = put_contents
    return http, put


def test_publish_new_pack_appends_entry(tmp_path):
    mp = tmp_path / "net-0.2.mrpack"
    mp.write_bytes(b"zip")
    http, put = _gh({"format": 1, "launcher": {"version": "0.1.0", "urls": {}}, "packs": [vars(entry("other", "1.0"))]})
    url = author.publish(http, REPO, "tok", entry("net", "0.2"), mp)
    assert url == "https://github.com/r/7"
    rel = next(c for c in http.calls if c.url.endswith("/releases"))
    assert rel.body["tag_name"] == "net-v0.2" and rel.body["make_latest"] == "false"
    assert rel.headers["Authorization"] == "Bearer tok"
    packs = json.loads(base64.b64decode(put["body"]["content"]))["packs"]
    assert [p["id"] for p in packs] == ["other", "net"] and put["body"]["sha"] == "abc"
    assert packs[1]["mrpack_url"] == "https://github.com/dl/net-0.2.mrpack" and packs[1]["mrpack_sha1"] == sha1(b"zip")


def test_publish_update_replaces_entry_and_creates_catalog(tmp_path):
    mp = tmp_path / "net-0.2.mrpack"
    mp.write_bytes(b"zip")
    http, put = _gh({"format": 1, "packs": [vars(entry("net", "0.1"))]})
    author.publish(http, REPO, "tok", entry("net", "0.2"), mp)
    packs = json.loads(base64.b64decode(put["body"]["content"]))["packs"]
    assert [(p["id"], p["version"]) for p in packs] == [("net", "0.2")]
    http, put = _gh(None)
    author.publish(http, REPO, "tok", entry("net", "0.2"), mp)
    assert "sha" not in put["body"]
    assert json.loads(base64.b64decode(put["body"]["content"]))["packs"][0]["id"] == "net"


def test_new_pack_id():
    assert author.new_pack_id(".NET", set()) == "net"
    assert author.new_pack_id("Мой пак", set()) == "moi-pak"
    assert author.new_pack_id(".NET", {"net"}) == "net-2"
    assert author.new_pack_id("!!!", set()) == "pack"


def test_import_skips_logs(tmp_path):
    inst = tmp_path / "instances" / "1.21.1"
    (inst / "minecraft" / "mods").mkdir(parents=True)
    (inst / "minecraft" / "mods" / "a.jar").write_bytes(b"a")
    (inst / "minecraft" / "saves" / "Новый мир").mkdir(parents=True)
    (inst / "minecraft" / "logs").mkdir()
    (inst / "minecraft" / "logs" / "latest.log").write_text("x")
    (inst / "minecraft" / "options.txt").write_text("lang:ru_ru")
    (inst / "instance.cfg").write_text("[General]\nname=1.21.1\n")
    (inst / "mmc-pack.json").write_text(json.dumps({"components": [
        {"uid": "org.lwjgl3", "version": "3.3.3"}, {"uid": "net.minecraft", "version": "1.21.1"},
        {"uid": "net.neoforged", "version": "21.1.267"}]}))
    assert importer.read_versions(inst) == ("1.21.1", "neoforge", "21.1.267")
    gd = tmp_path / "game"
    importer.import_instance(inst, gd)
    assert (gd / "mods" / "a.jar").exists() and (gd / "saves" / "Новый мир").is_dir()
    assert (gd / "options.txt").exists() and not (gd / "logs").exists()


def test_find_instances(tmp_path, monkeypatch):
    base = tmp_path / ".local" / "share" / "ElyPrismLauncher" / "instances"
    (base / "1.21.1").mkdir(parents=True)
    (base / "1.21.1" / "instance.cfg").write_text("")
    (base / "junk").mkdir()
    monkeypatch.setattr(importer.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert importer.find_instances() == [base / "1.21.1"]
