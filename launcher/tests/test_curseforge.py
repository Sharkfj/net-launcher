import json

import pytest

from netlauncher import author
from netlauncher.curseforge import API, CurseForge, NotDistributable, fingerprint, murmur2
from netlauncher.modrinth import API as MR_API, Modrinth
from tests.fakes import FakeHttp, sha1
from tests.jars import jar_bytes, toml_for


@pytest.mark.parametrize("data,expected", [(b"", 1540447798), (b"a", 626045324), (b"abcd", 3376380438),
                                           (b"helloworld", 2824650221)])
def test_murmur2_known_value(data, expected):
    assert murmur2(data) == expected


def test_fingerprint_ignores_whitespace(tmp_path):
    p = tmp_path / "a.jar"
    p.write_bytes(b"hello world\n")
    assert fingerprint(p) == 2824650221


def mod(mid=123, name="Create: Chromeware", dist=True):
    return {"id": mid, "name": name, "slug": "create-chromeware", "summary": "Импланты для Create",
            "downloadCount": 54321, "logo": {"thumbnailUrl": "https://media.forgecdn.net/x.png"},
            "links": {"websiteUrl": f"https://www.curseforge.com/minecraft/mc-mods/m{mid}"},
            "allowModDistribution": dist, "classId": 6}


def cffile(fid, mid=123, rtype=1, date="2026-11-14T10:00:00Z", url=True, deps=(), data=b"jar"):
    return {"id": fid, "modId": mid, "displayName": f"v{fid}", "fileName": f"f{fid}.jar", "releaseType": rtype,
            "fileDate": date, "downloadUrl": f"https://edge.forgecdn.net/files/{fid}/f{fid}.jar" if url else None,
            "hashes": [{"value": sha1(data), "algo": 1}, {"value": "md5", "algo": 2}], "fileLength": len(data),
            "dependencies": [{"modId": d, "relationType": 3} for d in deps] + [{"modId": 999, "relationType": 2}],
            "gameVersions": ["1.21.1", "NeoForge"]}


def test_search_maps_projects():
    http = FakeHttp({f"{API}/mods/search": {"data": [mod()]}})
    [p] = CurseForge(http, "KEY").search("chrome", "mod", "1.21.1", "neoforge")
    call = http.calls[-1]
    assert call.headers["x-api-key"] == "KEY"
    assert call.params["gameId"] == 432 and call.params["classId"] == 6 and call.params["modLoaderType"] == 6
    assert call.params["gameVersion"] == "1.21.1" and call.params["searchFilter"] == "chrome"
    assert p.id == "cf:123" and p.title == "Create: Chromeware" and p.downloads == 54321
    assert p.icon_url == "https://media.forgecdn.net/x.png"


def test_best_version_prefers_release_and_deps():
    http = FakeHttp({f"{API}/mods/123/files": {"data": [cffile(2, rtype=2, date="2026-11-15T00:00:00Z"),
                                                         cffile(1, deps=[77])]}})
    v = CurseForge(http, "KEY").best_version("cf:123", "1.21.1", "neoforge")
    assert v.id == "cf:1" and v.project_id == "cf:123" and v.required_deps == ["cf:77"]
    assert v.primary_file.url == "https://edge.forgecdn.net/files/1/f1.jar" and v.primary_file.sha1 == sha1(b"jar")
    assert http.calls[-1].params["modLoaderType"] == 6


def test_not_distributable():
    http = FakeHttp({f"{API}/mods/123/files": {"data": [cffile(5, url=False)]},
                     f"{API}/mods": {"data": [mod(dist=False)]}})
    with pytest.raises(NotDistributable) as e:
        CurseForge(http, "KEY").best_version("cf:123", "1.21.1", "neoforge")
    assert e.value.page_url == "https://www.curseforge.com/minecraft/mc-mods/m123/files/5"


def test_projects_batch():
    http = FakeHttp({f"{API}/mods": {"data": [mod(1, "A"), mod(2, "B")]}})
    got = CurseForge(http, "KEY").projects(["cf:1", "cf:2"])
    assert http.calls[-1].body == {"modIds": [1, 2]} and got["cf:2"].title == "B"


def test_build_uses_curseforge_url_and_exact_page(tmp_path):
    gd = tmp_path / "сборка"
    (gd / "mods").mkdir(parents=True)
    ok = jar_bytes(toml=toml_for("cinematic", "Cinematic Interaction", license="All Rights Reserved"))
    closed = jar_bytes(toml=toml_for("chromeware", "Create: Chromeware", license="All Rights Reserved"))
    (gd / "mods" / "cinematic.jar").write_bytes(ok)
    (gd / "mods" / "chromeware.jar").write_bytes(closed)
    fp_ok, fp_closed = fingerprint(gd / "mods" / "cinematic.jar"), fingerprint(gd / "mods" / "chromeware.jar")
    mr_http = FakeHttp({f"{MR_API}/version_files": {}, f"{MR_API}/projects": []})
    cf_http = FakeHttp({
        f"{API}/fingerprints/432": {"data": {"exactMatches": [
            {"id": 10, "file": cffile(100, mid=10, data=ok)},
            {"id": 20, "file": cffile(200, mid=20, url=False, data=closed)}],
            "exactFingerprints": [fp_ok, fp_closed]}},
        f"{API}/mods": {"data": [mod(10, "Cinematic Interaction"), mod(20, "Create: Chromeware", dist=False)]}})
    res = author.build(gd, Modrinth(mr_http), ".NET", "0.1", "1.21.1", "neoforge", "21.1.267", "", None,
                       cf=CurseForge(cf_http, "KEY"))
    [f] = res.index.files
    assert f.path == "mods/cinematic.jar" and f.urls == ["https://edge.forgecdn.net/files/100/f100.jar"]
    [m] = res.index.manual
    assert m.page_url == "https://www.curseforge.com/minecraft/mc-mods/m20/files/200"
    assert sorted(cf_http.calls[0].body["fingerprints"]) == sorted([fp_ok, fp_closed])


def test_curseforge_via_proxy_sends_no_key(home):
    from netlauncher.auth_ely import Account
    from netlauncher.catalog import parse
    from netlauncher.curseforge import for_context
    from netlauncher.friends import ELY_JOIN
    from netlauncher.ui.app import make_context

    base = "https://friends.example"
    http = FakeHttp({base + "/cf/mods/search": {"data": [mod()]}, base + "/cf/mods/123": {"data": mod()},
                     base + "/cf/mods/123/files/2": {"data": cffile(2)}, ELY_JOIN: None,
                     base + "/v1/auth/challenge": {"server_id": "sid"},
                     base + "/v1/auth/verify": {"token": "session", "name": "Player"}})
    ctx = make_context(home, http)
    ctx.accounts.save(Account("Player", "abc", "tok", "ct"))
    ctx.catalog = parse({"friends": {"url": base}})
    assert ctx.catalog.curseforge_proxy == base + "/cf"
    cf = for_context(ctx)
    assert cf.search("chrom", "mod", "1.21.1", "neoforge")[0].id == "cf:123"
    assert cf.projects(["cf:123"])["cf:123"].slug == "create-chromeware"
    assert cf.file(123, 2)["id"] == 2
    calls = [c for c in http.calls if "/cf/" in c.url]
    assert len(calls) == 3
    assert all(c.method == "GET" and c.headers == {"Authorization": "Bearer session"} for c in calls)
    assert calls[0].params["gameVersion"] == "1.21.1"
