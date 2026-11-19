"""Ely.by (Yggdrasil-compatible) login. Only tokens are kept, never the password."""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from netlauncher.net import Http, HttpError, Offline

AUTH = "https://authserver.ely.by/auth"


@dataclass
class Account:
    name: str
    uuid: str
    access_token: str
    client_token: str


class BadCredentials(Exception):
    pass


class TwoFactorRequired(Exception):
    pass


class NeedLogin(Exception):
    pass


class AuthUnavailable(Exception):
    pass


def _message(e: HttpError) -> str:
    try:
        return str(json.loads(e.body).get("errorMessage", ""))
    except (ValueError, AttributeError):
        return e.body or ""


def _account(r: dict) -> Account:
    prof = r.get("selectedProfile") or {}
    return Account(prof.get("name", ""), prof.get("id", ""), r["accessToken"], r["clientToken"])


class ElyAuth:
    def __init__(self, http: Http):
        self.http = http

    def _post(self, endpoint: str, body: dict):
        return self.http.post_json(f"{AUTH}/{endpoint}", body)

    def login(self, username: str, password: str, totp: str | None = None) -> Account:
        body = {"username": username, "password": f"{password}:{totp}" if totp else password,
                "clientToken": uuid.uuid4().hex, "requestUser": True}
        try:
            return _account(self._post("authenticate", body))
        except Offline as e:
            raise AuthUnavailable(str(e)) from e
        except HttpError as e:
            if e.status >= 500:
                raise AuthUnavailable(str(e)) from e
            if "two factor" in _message(e).lower():
                raise TwoFactorRequired() from e
            raise BadCredentials(_message(e)) from e

    def refresh(self, acc: Account) -> Account:
        r = self._post("refresh", {"accessToken": acc.access_token, "clientToken": acc.client_token,
                                   "requestUser": True})
        return _account(r)

    def validate(self, acc: Account) -> bool:
        try:
            self._post("validate", {"accessToken": acc.access_token})
        except HttpError as e:
            if e.status >= 500:
                raise AuthUnavailable(str(e)) from e
            return False
        return True

    def logout(self, acc: Account) -> None:
        try:
            self._post("invalidate", {"accessToken": acc.access_token, "clientToken": acc.client_token})
        except (HttpError, Offline):
            pass


class AccountStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> Account | None:
        try:
            return Account(**json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def save(self, acc: Account) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(acc), f)
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def ensure_valid(auth: ElyAuth, store: AccountStore) -> Account:
    acc = store.load()
    if acc is None:
        raise NeedLogin()
    try:
        if auth.validate(acc):
            return acc
    except (Offline, AuthUnavailable):
        return acc  # no internet: let offline singleplayer start with the stored account
    try:
        fresh = auth.refresh(acc)
    except (Offline, AuthUnavailable):
        return acc
    except HttpError as e:
        if e.status >= 500:
            return acc
        store.clear()
        raise NeedLogin() from e
    store.save(fresh)
    return fresh


def head_url(acc: Account) -> str:
    return f"https://skinsystem.ely.by/skins/{acc.name}.png"
