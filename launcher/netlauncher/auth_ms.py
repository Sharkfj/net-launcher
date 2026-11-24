"""Microsoft account sign-in (device code flow) for licensed Minecraft.

Mojang only serves apps whose Azure app id is on its allow list, so MS_CLIENT_ID stays empty and the
sign-in button stays disabled until an approved id exists. The flow:
device code -> Microsoft token -> Xbox Live -> XSTS -> login_with_xbox -> game ownership -> profile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode

from netlauncher.net import Http, HttpError

MS_CLIENT_ID = ""
SCOPE = "XboxLive.signin offline_access"
DEVICE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC = "https://api.minecraftservices.com"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


class MsLoginFailed(Exception):
    pass


class AppNotApproved(MsLoginFailed):
    """api.minecraftservices.com refused the app id (not on Mojang's allow list)."""


class NoGame(MsLoginFailed):
    """The Microsoft account does not own Minecraft: Java Edition."""


@dataclass
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int


@dataclass
class MsAccount:
    name: str
    uuid: str
    access_token: str


def _form(http: Http, url: str, fields: dict) -> dict:
    status, body = http.request("POST", url, data=urlencode(fields).encode(), headers=FORM)
    return json.loads(body or b"{}")


def start_device_login(http: Http, client_id: str) -> DeviceCode:
    d = _form(http, DEVICE_URL, {"client_id": client_id, "scope": SCOPE})
    return DeviceCode(d["device_code"], d["user_code"], d["verification_uri"], int(d.get("interval", 5)),
                      int(d.get("expires_in", 900)))


def poll_token(http: Http, client_id: str, code: DeviceCode) -> str | None:
    """Microsoft access token, or None while the player has not confirmed the code yet."""
    try:
        d = _form(http, TOKEN_URL, {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                    "client_id": client_id, "device_code": code.device_code})
    except HttpError as e:
        try:
            err = json.loads(e.body or "{}").get("error", "")
        except ValueError:
            err = ""
        if err in ("authorization_pending", "slow_down"):
            return None
        raise MsLoginFailed(err or str(e)) from e
    return d.get("access_token")


def minecraft_login(http: Http, ms_access_token: str) -> MsAccount:
    xbl = http.post_json(XBL_URL, {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com",
                                                  "RpsTicket": f"d={ms_access_token}"},
                                   "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})
    uhs = xbl["DisplayClaims"]["xui"][0]["uhs"]
    xsts = http.post_json(XSTS_URL, {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]},
                                     "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"})
    try:
        mc = http.post_json(f"{MC}/authentication/login_with_xbox", {"identityToken": f"XBL3.0 x={uhs};{xsts['Token']}"})
    except HttpError as e:
        if e.status == 403:
            raise AppNotApproved(str(e)) from e
        raise
    auth = {"Authorization": f"Bearer {mc['access_token']}"}
    owned = http.get_json(f"{MC}/entitlements/mcstore", headers=auth).get("items") or []
    if not owned:
        raise NoGame("no Minecraft: Java Edition on this account")
    try:
        prof = http.get_json(f"{MC}/minecraft/profile", headers=auth)
    except HttpError as e:
        if e.status == 404:
            raise NoGame("no Minecraft profile") from e
        raise
    return MsAccount(prof["name"], prof["id"], mc["access_token"])
