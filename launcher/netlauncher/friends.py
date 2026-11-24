"""Client for the friends service (server/friends_server.py)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable

from netlauncher.auth_ely import Account
from netlauncher.net import Http, HttpError

ELY_JOIN = "https://authserver.ely.by/session/join"


class NotConfigured(Exception):
    pass


class FriendsClient:
    def __init__(self, http: Http, base_url: str, session_path: Path, account: Callable[[], Account | None]):
        self.http, self.base = http, base_url.rstrip("/")
        self.session_path, self.account = Path(session_path), account
        acc = self.account()
        self.identity = acc.uuid if acc and not getattr(acc, "offline", False) else ""
        self._session_lock = threading.RLock()
        self.token = self._load()

    # ---------- session ----------
    def _load(self) -> str:
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8"))
            return data.get("token", "") if self.identity and data.get("uuid") == self.identity and data.get("base") == self.base else ""
        except (OSError, ValueError):
            return ""

    def _save(self) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.session_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"base": self.base, "uuid": self.identity, "token": self.token}, f)
            os.replace(tmp, self.session_path)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _active_account(self):
        acc = self.account()
        if not self.base or not self.identity or not acc or getattr(acc, "offline", False) or acc.uuid != self.identity:
            raise NotConfigured()
        return acc

    def login(self) -> str:
        with self._session_lock:
            return self._login()

    def _login(self) -> str:
        acc = self._active_account()
        sid = self.http.post_json(f"{self.base}/v1/auth/challenge", {})["server_id"]
        self.http.post_json(ELY_JOIN, {"accessToken": acc.access_token, "selectedProfile": acc.uuid, "serverId": sid})
        r = self.http.post_json(f"{self.base}/v1/auth/verify", {"name": acc.name, "server_id": sid})
        self._active_account()
        self.token = r["token"]
        self._save()
        return r.get("name", acc.name)

    def _call(self, path: str, body: dict | None = None, *, params: dict | None = None) -> dict:
        for attempt in (0, 1):
            with self._session_lock:
                self._active_account()
                if not self.token:
                    self._login()
                token = self.token
            headers = {"Authorization": f"Bearer {token}"}
            try:
                if body is None:
                    return self.http.get_json(f"{self.base}{path}", params=params, headers=headers)
                return self.http.post_json(f"{self.base}{path}", body, headers=headers)
            except HttpError as e:
                if e.status != 401 or attempt == 1:
                    raise
                with self._session_lock:
                    if self.token == token:
                        self.token = ""
        raise RuntimeError("unreachable")

    def chat(self, action, **data):
        return self._call("/v1/chat/" + action, data)

    def profile(self, name, action="read", **data):
        return self._call("/v1/profile", {"name": name, "action": action, **data})

    # ---------- api ----------
    def curseforge_get(self, path: str, params: dict | None = None) -> dict:
        return self._call("/cf/" + path, params=params)

    def issue_key(self) -> dict:
        return self._call("/v1/support/keys", {})

    def redeem_key(self, key: str) -> dict:
        return self._call("/v1/support/redeem", {"key": key})

    def state(self) -> dict:
        return self._call("/v1/state")

    def presence(self, status: str, pack: str = "", server: str = "", *, pack_id="", pack_version="") -> dict:
        identity = {"pack_id": pack_id, "pack_version": pack_version} if pack_id else {}
        return self._call("/v1/presence", {"status": status, "pack": pack, "server": server, **identity})

    def request(self, name: str) -> dict:
        return self._call("/v1/friends/request", {"name": name})

    def accept(self, name: str) -> dict:
        return self._call("/v1/friends/accept", {"name": name})

    def decline(self, name: str) -> dict:
        return self._call("/v1/friends/decline", {"name": name})

    def remove(self, name: str) -> dict:
        return self._call("/v1/friends/remove", {"name": name})

    def invite(self, name: str, pack: str, server: str, *, pack_id="", pack_version="") -> dict:
        identity = {"pack_id": pack_id, "pack_version": pack_version} if pack_id else {}
        return self._call("/v1/invite", {"name": name, "pack": pack, "server": server, **identity})

    def dismiss(self, name: str) -> dict:
        return self._call("/v1/invite/dismiss", {"from": name})
