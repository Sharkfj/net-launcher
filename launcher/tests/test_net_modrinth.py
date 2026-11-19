import hashlib
import http.server
import json
import threading

import pytest

import netlauncher
from netlauncher import net
from netlauncher.modrinth import API, Modrinth, search_loader
from netlauncher.net import HashMismatch, Offline, RequestsHttp
from tests.fakes import FakeHttp

PAYLOAD = b"jar-bytes" * 100


@pytest.fixture
def server():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/f.jar":
                self.send_response(200)
                self.send_header("Content-Length", str(len(PAYLOAD)))
                self.end_headers()
                self.wfile.write(PAYLOAD)
            elif self.path == "/ua":
                body = self.headers.get("User-Agent", "").encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"ua": body.decode()}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_user_agent():
    assert net.USER_AGENT == f"NETLauncher/{netlauncher.__version__}"


def test_requests_http_sends_user_agent(server):
    assert RequestsHttp().get_json(server + "/ua")["ua"] == net.USER_AGENT


def test_download_ok_with_progress(server, tmp_path):
    seen = []
    dest = tmp_path / "Моды" / "a.jar"
    RequestsHttp().download(server + "/f.jar", dest, sha1=hashlib.sha1(PAYLOAD).hexdigest(),
                            progress=lambda d, t: seen.append((d, t)))
    assert dest.read_bytes() == PAYLOAD and seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert not dest.with_name("a.jar.part").exists()


def test_download_verifies_and_cleans(server, tmp_path):
    with pytest.raises(HashMismatch):
        RequestsHttp().download(server + "/f.jar", tmp_path / "a.jar", sha1="0" * 40)
    assert not (tmp_path / "a.jar").exists() and not (tmp_path / "a.jar.part").exists()


def test_connection_refused_is_offline(tmp_path):
    with pytest.raises(Offline):
        RequestsHttp(retries=0).get_json("http://127.0.0.1:9/nothing")


def _version(vid, number, vtype, deps=(), date="2026-01-01"):
    return {"id": vid, "project_id": "p", "version_number": number, "version_type": vtype,
            "game_versions": ["1.21.1"], "loaders": ["neoforge"], "date_published": date,
            "dependencies": [{"project_id": d, "dependency_type": "required"} for d in deps]
            + [{"project_id": "opt", "dependency_type": "optional"}],
            "files": [{"url": f"https://cdn/{vid}.jar", "filename": f"{vid}.jar", "primary": True, "size": 3,
                       "hashes": {"sha1": "a" * 40, "sha512": "b" * 128}}]}


def test_best_version_prefers_release():
    fake = FakeHttp({f"{API}/project/p/version": [_version("v2", "2.0", "beta"), _version("v1", "1.9", "release")]})
    assert Modrinth(fake).best_version("p", "1.21.1", "neoforge").version_number == "1.9"


def test_best_version_falls_back_to_beta_when_no_release():
    fake = FakeHttp({f"{API}/project/p/version": [_version("v2", "2.0", "beta")]})
    assert Modrinth(fake).best_version("p", "1.21.1", "neoforge").version_number == "2.0"


def test_best_version_none():
    fake = FakeHttp({f"{API}/project/p/version": []})
    assert Modrinth(fake).best_version("p", "1.21.1", "neoforge") is None


def test_versions_params_and_required_deps():
    fake = FakeHttp({f"{API}/project/p/version": [_version("v1", "1.0", "release", deps=["dep1"])]})
    v = Modrinth(fake).versions("p", "1.21.1", "neoforge")[0]
    assert json.loads(fake.calls[-1].params["game_versions"]) == ["1.21.1"]
    assert json.loads(fake.calls[-1].params["loaders"]) == ["neoforge"]
    assert v.required_deps == ["dep1"] and v.primary_file.filename == "v1.jar"


def test_versions_without_loader_has_no_loader_param():
    fake = FakeHttp({f"{API}/project/p/version": []})
    Modrinth(fake).versions("p", "1.21.1", None)
    assert "loaders" not in fake.calls[-1].params


def test_search_facets():
    fake = FakeHttp({f"{API}/search": {"hits": [{"project_id": "x", "slug": "x", "title": "X", "description": "d",
                                                  "downloads": 5, "icon_url": "", "project_type": "mod",
                                                  "client_side": "required", "server_side": "optional"}]}})
    hits = Modrinth(fake).search("rain", "mod", "1.21.1", "neoforge")
    facets = json.loads(fake.calls[-1].params["facets"])
    assert ["versions:1.21.1"] in facets and ["categories:neoforge"] in facets and ["project_type:mod"] in facets
    assert hits[0].id == "x" and hits[0].client_side == "required"


def test_search_without_loader_facet():
    fake = FakeHttp({f"{API}/search": {"hits": []}})
    Modrinth(fake).search("", "resourcepack", "1.21.1", None)
    facets = json.loads(fake.calls[-1].params["facets"])
    assert not any(f[0].startswith("categories:") for f in facets)


def test_versions_by_hash_and_latest():
    v = _version("v1", "1.0", "release")
    fake = FakeHttp({f"{API}/version_files": {"abc": v}, f"{API}/version_files/update": {"abc": v}})
    mr = Modrinth(fake)
    assert mr.versions_by_hash(["abc"])["abc"].id == "v1"
    assert mr.latest_by_hash(["abc"], "1.21.1", "neoforge")["abc"].id == "v1"
    body = fake.calls[-1].body
    assert body["loaders"] == ["neoforge"] and body["game_versions"] == ["1.21.1"] and body["algorithm"] == "sha1"


def test_versions_by_hash_empty_makes_no_call():
    fake = FakeHttp()
    assert Modrinth(fake).versions_by_hash([]) == {} and fake.calls == []


def test_projects():
    fake = FakeHttp({f"{API}/projects": [{"id": "a", "slug": "aa", "title": "A", "description": "", "downloads": 1,
                                          "icon_url": None, "project_type": "mod", "client_side": "required",
                                          "server_side": "unsupported"}]})
    p = Modrinth(fake).projects(["a"])["a"]
    assert p.slug == "aa" and p.server_side == "unsupported" and p.icon_url == ""


def test_search_loader():
    assert search_loader("mod", "neoforge") == "neoforge"
    assert search_loader("shader", "neoforge") == "iris"
    assert search_loader("resourcepack", "neoforge") is None
