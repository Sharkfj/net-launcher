"""Microsoft account sign-in (device code flow) for licensed Minecraft.

Mojang only serves apps whose Azure app id is on its allow list, so the sign-in button requires an approved client ID. The flow:
device code -> Microsoft token -> Xbox Live -> XSTS -> login_with_xbox -> game ownership -> profile.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlencode

from netlauncher.net import Http, HttpError

from netlauncher.auth_ely import Account

try:
    from netlauncher._build_config import MICROSOFT_CLIENT_ID
except ImportError:
    MICROSOFT_CLIENT_ID = ""

MS_CLIENT_ID = os.getenv("NET_MICROSOFT_CLIENT_ID", MICROSOFT_CLIENT_ID).strip()
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


def poll_credentials(http: Http, client_id: str, code: DeviceCode) -> dict | None:
    try:
        d = _form(http, TOKEN_URL, {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                    "client_id": client_id, "device_code": code.device_code})
    except HttpError as e:
        try:
            err = json.loads(e.body or "{}").get("error", "")
        except ValueError:
            err = ""
        if err == "slow_down":
            code.interval += 5
        if err in ("authorization_pending", "slow_down"):
            return None
        raise MsLoginFailed(err or str(e)) from e
    return d


def poll_token(http: Http, client_id: str, code: DeviceCode) -> str | None:
    return (poll_credentials(http, client_id, code) or {}).get("access_token")


def account_from_credentials(http: Http, tokens: dict, refresh_token: str = "") -> Account:
    profile = minecraft_login(http, tokens["access_token"])
    return Account(profile.name, profile.uuid, profile.access_token, "",
                   provider="microsoft", refresh_token=tokens.get("refresh_token") or refresh_token)


def refresh_account(http: Http, account: Account) -> Account:
    if not MS_CLIENT_ID or not account.refresh_token:
        raise MsLoginFailed("Microsoft sign-in required")
    tokens = _form(http, TOKEN_URL, {"grant_type": "refresh_token", "client_id": MS_CLIENT_ID,
                                    "refresh_token": account.refresh_token, "scope": SCOPE})
    fresh = account_from_credentials(http, tokens, account.refresh_token)
    if fresh.uuid != account.uuid:
        raise MsLoginFailed("Minecraft account changed")
    return fresh


def fetch_skin(http: Http, account: Account, cache_dir, force=False):
    from netlauncher.skin import fetch_texture

    def texture():
        profile = http.get_json(f"{MC}/minecraft/profile",
                                headers={"Authorization": f"Bearer {account.access_token}"})
        skin = next((item for item in profile.get("skins", []) if item.get("state") == "ACTIVE"), None)
        if skin:
            from urllib.parse import urlparse
            url = urlparse(skin["url"])
            if url.scheme in ("http", "https") and url.netloc == "textures.minecraft.net":
                return skin["url"].replace("http://", "https://", 1), skin.get("variant") == "SLIM"
        return None

    return fetch_texture(http, "microsoft-" + account.uuid, cache_dir, force, texture)


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
