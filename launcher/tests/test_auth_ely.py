import json
import os
import sys

import pytest

from netlauncher.auth_ely import (AUTH, Account, AccountStore, AuthUnavailable, BadCredentials, ElyAuth, NeedLogin,
                                  TwoFactorRequired, ensure_valid, head_url)
from netlauncher.net import HttpError
from tests.fakes import FakeHttp

OK = {"accessToken": "tok1", "clientToken": "ct", "selectedProfile": {"id": "abc123", "name": "Shark"}}


def err(status, msg):
    return HttpError(status, "x", json.dumps({"error": "ForbiddenOperationException", "errorMessage": msg}))


def test_login_ok_stores_no_password(tmp_path):
    http = FakeHttp({f"{AUTH}/authenticate": OK})
    acc = ElyAuth(http).login("shark@mail", "секрет")
    assert acc == Account("Shark", "abc123", "tok1", "ct")
    body = http.calls[-1].body
    assert body["username"] == "shark@mail" and body["requestUser"] is True and body["clientToken"]
    store = AccountStore(tmp_path / "accounts.json")
    store.save(acc)
    assert "секрет" not in (tmp_path / "accounts.json").read_text(encoding="utf-8")
    assert store.load() == acc


def test_login_2fa_required():
    http = FakeHttp({f"{AUTH}/authenticate": err(401, "Account protected with two factor auth.")})
    with pytest.raises(TwoFactorRequired):
        ElyAuth(http).login("u", "p")


def test_login_with_totp_concats():
    http = FakeHttp({f"{AUTH}/authenticate": OK})
    ElyAuth(http).login("u", "pass", totp="123456")
    assert http.calls[-1].body["password"] == "pass:123456"


def test_bad_credentials():
    http = FakeHttp({f"{AUTH}/authenticate": err(401, "Invalid credentials. Invalid nickname or password.")})
    with pytest.raises(BadCredentials):
        ElyAuth(http).login("u", "p")


def test_login_server_down_is_unavailable():
    http = FakeHttp({f"{AUTH}/authenticate": HttpError(502, "x")})
    with pytest.raises(AuthUnavailable):
        ElyAuth(http).login("u", "p")
    with pytest.raises(AuthUnavailable):
        ElyAuth(FakeHttp(offline=True)).login("u", "p")


def test_ensure_valid_refreshes_then_needs_login(tmp_path):
    store = AccountStore(tmp_path / "accounts.json")
    store.save(Account("Shark", "abc123", "old", "ct"))
    http = FakeHttp({f"{AUTH}/validate": err(401, "Token expired."),
                     f"{AUTH}/refresh": {**OK, "accessToken": "new"}})
    assert ensure_valid(ElyAuth(http), store).access_token == "new"
    assert store.load().access_token == "new"
    assert http.calls[-1].body == {"accessToken": "old", "clientToken": "ct", "requestUser": True}
    http.routes[f"{AUTH}/refresh"] = err(401, "Token does not exist.")
    with pytest.raises(NeedLogin):
        ensure_valid(ElyAuth(http), store)
    assert store.load() is None


def test_ensure_valid_ok_and_offline(tmp_path):
    store = AccountStore(tmp_path / "accounts.json")
    acc = Account("Shark", "abc123", "tok", "ct")
    store.save(acc)
    assert ensure_valid(ElyAuth(FakeHttp({f"{AUTH}/validate": None})), store) == acc
    assert ensure_valid(ElyAuth(FakeHttp(offline=True)), store) == acc


def test_ensure_valid_without_account(tmp_path):
    with pytest.raises(NeedLogin):
        ensure_valid(ElyAuth(FakeHttp()), AccountStore(tmp_path / "none.json"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_store_mode_600(tmp_path):
    p = tmp_path / "accounts.json"
    AccountStore(p).save(Account("a", "b", "c", "d"))
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"


def test_logout_and_head_url():
    http = FakeHttp({f"{AUTH}/invalidate": None})
    ElyAuth(http).logout(Account("Shark", "abc", "tok", "ct"))
    assert http.calls[-1].body == {"accessToken": "tok", "clientToken": "ct"}
    assert head_url(Account("Shark", "abc", "t", "c")) == "https://skinsystem.ely.by/skins/Shark.png"
