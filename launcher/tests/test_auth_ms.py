import json

import pytest

from netlauncher import auth_ms
from netlauncher.net import HttpError
from tests.fakes import FakeHttp

MC = "https://api.minecraftservices.com"


def _routes(xbox_ok=True, owns=True):
    r = {
        ("POST", auth_ms.DEVICE_URL): {"device_code": "dev", "user_code": "ABCD-1234", "interval": 5, "expires_in": 900,
                                       "verification_uri": "https://www.microsoft.com/link"},
        ("POST", auth_ms.TOKEN_URL): {"access_token": "ms-at", "refresh_token": "ms-rt"},
        auth_ms.XBL_URL: {"Token": "xbl", "DisplayClaims": {"xui": [{"uhs": "hash1"}]}},
        auth_ms.XSTS_URL: {"Token": "xsts", "DisplayClaims": {"xui": [{"uhs": "hash1"}]}},
        f"{MC}/authentication/login_with_xbox": {"access_token": "mc-at", "expires_in": 86400} if xbox_ok
        else HttpError(403, f"{MC}/authentication/login_with_xbox", json.dumps({"error": "Invalid app registration"})),
        f"{MC}/entitlements/mcstore": {"items": [{"name": "game_minecraft"}] if owns else []},
        f"{MC}/minecraft/profile": {"id": "0123abcd", "name": "Shark"},
    }
    return r


def test_client_id_empty_until_approved():
    assert auth_ms.MS_CLIENT_ID == ""


def test_device_login_and_poll():
    http = FakeHttp(_routes())
    code = auth_ms.start_device_login(http, "cid")
    assert code.user_code == "ABCD-1234" and code.verification_uri == "https://www.microsoft.com/link"
    assert code.device_code == "dev" and code.interval == 5
    assert auth_ms.poll_token(http, "cid", code) == "ms-at"


def test_poll_pending_returns_none():
    pending = HttpError(400, auth_ms.TOKEN_URL, json.dumps({"error": "authorization_pending"}))
    http = FakeHttp({**_routes(), ("POST", auth_ms.TOKEN_URL): pending})
    code = auth_ms.start_device_login(http, "cid")
    assert auth_ms.poll_token(http, "cid", code) is None


def test_full_path_to_account():
    http = FakeHttp(_routes())
    acc = auth_ms.minecraft_login(http, "ms-at")
    assert acc == auth_ms.MsAccount("Shark", "0123abcd", "mc-at")
    xbox = next(c for c in http.calls if c.url == f"{MC}/authentication/login_with_xbox")
    assert xbox.body == {"identityToken": "XBL3.0 x=hash1;xsts"}


def test_not_approved_app():
    with pytest.raises(auth_ms.AppNotApproved):
        auth_ms.minecraft_login(FakeHttp(_routes(xbox_ok=False)), "ms-at")


def test_account_without_game():
    with pytest.raises(auth_ms.NoGame):
        auth_ms.minecraft_login(FakeHttp(_routes(owns=False)), "ms-at")
