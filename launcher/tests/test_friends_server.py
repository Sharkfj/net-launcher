import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
import friends_server  # noqa: E402


@pytest.fixture
def srv(tmp_path):
    joined = set()   # (name, server_id) pairs "joined" at Ely.by

    def verifier(name, server_id):
        return {"id": f"uuid-{name}", "name": name} if (name, server_id) in joined else None

    httpd = friends_server.make_server("127.0.0.1", 0, tmp_path / "f.db", verifier)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, joined, httpd
    httpd.shutdown()


def call(base, path, body=None, token=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def login(base, joined, name):
    _, ch = call(base, "/v1/auth/challenge", {})
    joined.add((name, ch["server_id"]))
    st, r = call(base, "/v1/auth/verify", {"name": name, "server_id": ch["server_id"]})
    assert st == 200
    return r["token"]


def test_auth_requires_ely_join(srv):
    base, joined, _ = srv
    _, ch = call(base, "/v1/auth/challenge", {})
    st, _ = call(base, "/v1/auth/verify", {"name": "Shark", "server_id": ch["server_id"]})
    assert st == 401
    assert call(base, "/v1/state")[0] == 401
    tok = login(base, joined, "Shark")
    st, me = call(base, "/v1/state", token=tok)
    assert st == 200 and me["me"] == "Shark" and me["friends"] == []


def test_challenge_single_use(srv):
    base, joined, _ = srv
    _, ch = call(base, "/v1/auth/challenge", {})
    joined.add(("Shark", ch["server_id"]))
    assert call(base, "/v1/auth/verify", {"name": "Shark", "server_id": ch["server_id"]})[0] == 200
    assert call(base, "/v1/auth/verify", {"name": "Shark", "server_id": ch["server_id"]})[0] == 401


def test_request_accept_presence_invite(srv):
    base, joined, _ = srv
    a, b = login(base, joined, "Shark"), login(base, joined, "Vasya")
    assert call(base, "/v1/friends/request", {"name": "vasya"}, a)[0] == 200
    st = call(base, "/v1/state", token=b)[1]
    assert st["incoming"] == ["Shark"] and call(base, "/v1/state", token=a)[1]["outgoing"] == ["Vasya"]
    call(base, "/v1/friends/accept", {"name": "Shark"}, b)
    call(base, "/v1/presence", {"status": "playing", "pack": ".NET", "server": "play.example.net"}, b)
    friends = call(base, "/v1/state", token=a)[1]["friends"]
    assert friends == [{"name": "Vasya", "online": True, "status": "playing", "pack": ".NET",
                        "server": "play.example.net", "last_seen": friends[0]["last_seen"]}]
    assert call(base, "/v1/invite", {"name": "Vasya", "pack": ".NET", "server": "play.example.net"}, a)[0] == 200
    inv = call(base, "/v1/state", token=b)[1]["invites"]
    assert [(i["from"], i["pack"], i["server"]) for i in inv] == [("Shark", ".NET", "play.example.net")]
    call(base, "/v1/invite/dismiss", {"from": "Shark"}, b)
    assert call(base, "/v1/state", token=b)[1]["invites"] == []
    call(base, "/v1/friends/remove", {"name": "Vasya"}, a)
    assert call(base, "/v1/state", token=b)[1]["friends"] == []


def test_mutual_requests_become_friends_and_decline(srv):
    base, joined, _ = srv
    a, b, c = (login(base, joined, n) for n in ("Shark", "Vasya", "Petya"))
    call(base, "/v1/friends/request", {"name": "Vasya"}, a)
    call(base, "/v1/friends/request", {"name": "Shark"}, b)
    assert [f["name"] for f in call(base, "/v1/state", token=a)[1]["friends"]] == ["Vasya"]
    call(base, "/v1/friends/request", {"name": "Shark"}, c)
    call(base, "/v1/friends/decline", {"name": "Petya"}, a)
    assert call(base, "/v1/state", token=a)[1]["incoming"] == []


def test_invite_only_friends_and_validation(srv):
    base, joined, _ = srv
    a = login(base, joined, "Shark")
    login(base, joined, "Vasya")
    assert call(base, "/v1/invite", {"name": "Vasya", "pack": "x", "server": ""}, a)[0] == 403
    assert call(base, "/v1/friends/request", {"name": "bad name!"}, a)[0] == 400
    assert call(base, "/v1/friends/request", {"name": "Shark"}, a)[0] == 400


def test_offline_after_timeout(srv, monkeypatch):
    base, joined, _ = srv
    a, b = login(base, joined, "Shark"), login(base, joined, "Vasya")
    call(base, "/v1/friends/request", {"name": "Vasya"}, a)
    call(base, "/v1/friends/accept", {"name": "Shark"}, b)
    call(base, "/v1/presence", {"status": "launcher"}, b)
    real = time.time
    monkeypatch.setattr(friends_server.time, "time", lambda: real() + 120)
    assert call(base, "/v1/state", token=a)[1]["friends"][0]["online"] is False
