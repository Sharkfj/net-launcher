import json

import pytest

from netlauncher import snapshots
from netlauncher.library import AlreadyInstalled, Library, Locked
from netlauncher.modrinth import API, Modrinth
from tests.fakes import FakeHttp, sha1, sha512
from tests.jars import jar_bytes, toml_for

CLOTH = jar_bytes(toml=toml_for("cloth_config", "Cloth Config"))
TECTONIC = jar_bytes(toml=toml_for("tectonic"), nested={"apollib.jar": jar_bytes(toml=toml_for("apollib"))})
SHOULDER = jar_bytes(toml=toml_for("shouldersurfing", "Shoulder Surfing"))
NEWLIB = jar_bytes(toml=toml_for("newlib"))
APOLLIB = jar_bytes(toml=toml_for("apollib"))
WALKERS = jar_bytes(toml=toml_for("walkers"))


def _ver(pid, vid, data, vtype="release", deps=(), date="2026-05-01"):
    return {"id": vid, "project_id": pid, "version_number": vid, "version_type": vtype,
            "game_versions": ["1.21.1"], "loaders": ["neoforge"], "date_published": date,
            "dependencies": [{"project_id": d, "dependency_type": "required"} for d in deps],
            "files": [{"url": f"https://cdn/{vid}.jar", "filename": f"{vid}.jar", "primary": True,
                       "size": len(data), "hashes": {"sha1": sha1(data), "sha512": sha512(data)}}]}


def _proj(pid):
    return {"id": pid, "slug": pid, "title": pid.title(), "description": "", "downloads": 1, "icon_url": "",
            "project_type": "mod", "client_side": "required", "server_side": "required"}


class World:
    def __init__(self, tmp_path):
        self.gd = tmp_path / "игра"
        (self.gd / "mods").mkdir(parents=True)
        self.snaps = tmp_path / "snaps"
        self.by_hash = {}        # sha1 -> version json (installed files known to Modrinth)
        self.versions = {}       # pid -> [version json]
        self.updates = {}        # sha1 -> version json
        self.http = FakeHttp({
            f"{API}/version_files": lambda c: {h: self.by_hash[h] for h in c.body["hashes"] if h in self.by_hash},
            f"{API}/version_files/update": lambda c: {h: self.updates[h] for h in c.body["hashes"] if h in self.updates},
            f"{API}/projects": lambda c: [_proj(i) for i in json.loads(c.params["ids"])],
        })

    def add_project(self, pid, versions):
        self.versions[pid] = versions
        self.http.routes[f"{API}/project/{pid}/version"] = versions

    def installed(self, name, data, version_json=None):
        (self.gd / "mods" / name).write_bytes(data)
        if version_json:
            self.by_hash[sha1(data)] = version_json

    def serve(self, version_json, data):
        self.http.downloads[version_json["files"][0]["url"]] = data

    def lib(self, pack_state=None):
        return Library(self.gd, self.snaps, Modrinth(self.http), self.http, self.gd.parent / "cache",
                       "1.21.1", "neoforge", pack_state=pack_state)


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_scan_and_toggle(w):
    w.installed("cloth.jar", CLOTH)
    lib = w.lib()
    [item] = lib.scan("mod")
    assert item.name == "Cloth Config" and item.enabled and not item.from_pack
    off = lib.set_enabled(item, False)
    assert not off.enabled and (w.gd / "mods" / "cloth.jar.disabled").exists()
    assert snapshots.list_snapshots(w.snaps)[0].reason == "Выключение: Cloth Config"
    on = lib.set_enabled(off, True)
    assert on.enabled and (w.gd / "mods" / "cloth.jar").exists()


def test_scan_ignores_non_content(w):
    (w.gd / "shaderpacks").mkdir()
    (w.gd / "shaderpacks" / "Complementary.zip").write_bytes(b"zip")
    (w.gd / "shaderpacks" / "Complementary.zip.txt").write_text("x")
    items = w.lib().scan("shader")
    assert [i.path.name for i in items] == ["Complementary.zip"] and items[0].name == "Complementary"


def test_locked_pack_mod_cannot_be_disabled(w):
    w.installed("cloth.jar", CLOTH)
    w.installed("fog.jar", NEWLIB)
    state = {"mods/cloth.jar": {"sha1": sha1(CLOTH), "client": "required", "server": "required"},
             "mods/fog.jar": {"sha1": sha1(NEWLIB), "client": "required", "server": "unsupported"}}
    lib = w.lib(state)
    cloth, fog = sorted(lib.scan("mod"), key=lambda i: i.path.name)
    assert cloth.locked and cloth.from_pack and fog.from_pack and not fog.locked
    with pytest.raises(Locked):
        lib.set_enabled(cloth, False)
    with pytest.raises(Locked):
        lib.remove(cloth)
    assert not lib.set_enabled(fog, False).enabled


def test_remove_snapshots_first(w):
    w.installed("cloth.jar", CLOTH)
    lib = w.lib()
    lib.remove(lib.scan("mod")[0])
    assert not (w.gd / "mods" / "cloth.jar").exists()
    assert (snapshots.list_snapshots(w.snaps)[0].path / "mods" / "cloth.jar").exists()


def test_install_resolves_deps_and_skips_present(w):
    w.installed("cloth.jar", CLOTH, _ver("cloth-config", "cloth-15", CLOTH))
    sh = _ver("shoulder", "shoulder-5", SHOULDER, deps=["cloth-config", "newlib"])
    nl = _ver("newlib", "newlib-1", NEWLIB)
    w.add_project("shoulder", [sh])
    w.add_project("newlib", [nl])
    w.serve(sh, SHOULDER)
    w.serve(nl, NEWLIB)
    lib = w.lib()
    plan = lib.plan_install("shoulder", "mod")
    assert [p.slug for p, _ in plan.items] == ["shoulder", "newlib"] and plan.skipped == ["cloth-config"]
    items = lib.install(plan, "mod")
    assert sorted(i.path.name for i in items) == ["newlib-1.jar", "shoulder-5.jar"]
    assert snapshots.list_snapshots(w.snaps)[0].reason == "Установка: Shoulder"


def test_install_already_installed(w):
    w.installed("cloth.jar", CLOTH, _ver("cloth-config", "cloth-15", CLOTH))
    with pytest.raises(AlreadyInstalled):
        w.lib().plan_install("cloth-config", "mod")


def test_install_discards_dup_modid_from_nested(w):
    w.installed("tectonic.jar", TECTONIC)
    wk = _ver("walkers", "walkers-1", WALKERS, deps=["apollib"])
    ap = _ver("apollib", "apollib-1", APOLLIB)
    w.add_project("walkers", [wk])
    w.add_project("apollib", [ap])
    w.serve(wk, WALKERS)
    w.serve(ap, APOLLIB)
    lib = w.lib()
    plan = lib.plan_install("walkers", "mod")
    items = lib.install(plan, "mod")
    assert [i.path.name for i in items] == ["walkers-1.jar"] and "apollib" in plan.skipped
    assert not (w.gd / "mods" / "apollib-1.jar").exists()


def test_updates_skip_beta_over_release(w):
    cur = _ver("cloth-config", "cloth-15", CLOTH)
    w.installed("cloth.jar", CLOTH, cur)
    w.updates[sha1(CLOTH)] = _ver("cloth-config", "cloth-16b", NEWLIB, vtype="beta", date="2026-09-01")
    assert w.lib().check_updates("mod") == []


def test_updates_found_and_applied_keep_disabled(w):
    cur = _ver("cloth-config", "cloth-15", CLOTH)
    w.installed("cloth.jar.disabled", CLOTH, cur)
    new = _ver("cloth-config", "cloth-16", NEWLIB, date="2026-09-01")
    w.updates[sha1(CLOTH)] = new
    w.serve(new, NEWLIB)
    lib = w.lib()
    [up] = lib.check_updates("mod")
    assert up.version.version_number == "cloth-16"
    [item] = lib.apply_updates([up])
    assert item.path.name == "cloth-16.jar.disabled" and not (w.gd / "mods" / "cloth.jar.disabled").exists()


def test_check_updates_ignores_pack_items(w):
    cur = _ver("cloth-config", "cloth-15", CLOTH)
    w.installed("cloth.jar", CLOTH, cur)
    w.updates[sha1(CLOTH)] = _ver("cloth-config", "cloth-16", NEWLIB, date="2026-09-01")
    state = {"mods/cloth.jar": {"sha1": sha1(CLOTH), "client": "required", "server": "unsupported"}}
    assert w.lib(state).check_updates("mod") == []
