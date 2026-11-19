import os
import sys

import pytest

from netlauncher import catalog
from netlauncher.auth_ely import Account
from netlauncher.friends import ELY_JOIN, FriendsClient, NotConfigured
from netlauncher.net import HttpError
from tests.fakes import FakeHttp

BASE = "https://friends.example.net"
ACC = Account("Shark", "uuid-1", "tok", "ct")


def routes(state=None):
    return {f"{BASE}/v1/auth/challenge": {"server_id": "sid1"}, ELY_JOIN: None,
            f"{BASE}/v1/auth/verify": {"token": "S1", "name": "Shark"},
            f"{BASE}/v1/state": state or {"me": "Shark", "friends": [], "incoming": [], "outgoing": [], "invites": []}}


def test_login_joins_ely_and_saves_token(tmp_path):
    http = FakeHttp(routes())
    c = FriendsClient(http, BASE, tmp_path / "fs.json", lambda: ACC)
    c.login()
    join = next(x for x in http.calls if x.url == ELY_JOIN)
    assert join.body == {"accessToken": "tok", "selectedProfile": "uuid-1", "serverId": "sid1"}
    verify = next(x for x in http.calls if x.url.endswith("/verify"))
    assert verify.body == {"name": "Shark", "server_id": "sid1"}
    assert FriendsClient(http, BASE, tmp_path / "fs.json", lambda: ACC).token == "S1"
    if sys.platform != "win32":
        assert oct(os.stat(tmp_path / "fs.json").st_mode & 0o777) == "0o600"


def test_state_logs_in_lazily_and_relogins_on_401(tmp_path):
    http = FakeHttp(routes())
    c = FriendsClient(http, BASE, tmp_path / "fs.json", lambda: ACC)
    assert c.state()["me"] == "Shark" and c.token == "S1"
    calls = {"n": 0}

    def state(call):
        calls["n"] += 1
        return HttpError(401, call.url) if calls["n"] == 1 else {"me": "Shark", "friends": [], "incoming": [],
                                                                    "outgoing": [], "invites": []}
    http.routes[f"{BASE}/v1/state"] = state
    http.routes[f"{BASE}/v1/auth/verify"] = {"token": "S2", "name": "Shark"}
    assert c.state()["me"] == "Shark" and c.token == "S2"
    assert next(x for x in reversed(http.calls) if x.url.endswith("/v1/state")).headers["Authorization"] == "Bearer S2"


def test_actions_send_bodies(tmp_path):
    http = FakeHttp(routes())
    for p in ("request", "accept", "decline", "remove", "dismiss"):
        http.routes[f"{BASE}/v1/friends/{p}" if p != "dismiss" else f"{BASE}/v1/invite/dismiss"] = routes()[f"{BASE}/v1/state"]
    http.routes[f"{BASE}/v1/invite"] = routes()[f"{BASE}/v1/state"]
    http.routes[f"{BASE}/v1/presence"] = routes()[f"{BASE}/v1/state"]
    c = FriendsClient(http, BASE, tmp_path / "fs.json", lambda: ACC)
    c.request("Vasya")
    assert http.calls[-1].body == {"name": "Vasya"}
    c.invite("Vasya", ".NET", "play.example.net")
    assert http.calls[-1].body == {"name": "Vasya", "pack": ".NET", "server": "play.example.net"}
    c.presence("playing", ".NET", "")
    assert http.calls[-1].body == {"status": "playing", "pack": ".NET", "server": ""}
    c.dismiss("Vasya")
    assert http.calls[-1].body == {"from": "Vasya"}


def test_not_configured(tmp_path):
    with pytest.raises(NotConfigured):
        FriendsClient(FakeHttp(), "", tmp_path / "fs.json", lambda: ACC).state()


def test_catalog_friends_url_roundtrip():
    cat = catalog.parse({"format": 1, "friends": {"url": BASE}, "packs": []})
    assert cat.friends_url == BASE
    assert catalog.to_json(cat)["friends"] == {"url": BASE}
    assert catalog.parse({"packs": []}).friends_url == ""
