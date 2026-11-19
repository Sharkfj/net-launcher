"""Client for the friends service (server/friends_server.py)."""

from __future__ import annotations

import json
import os
import sys
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
        self.token = self._load()

    # ---------- session ----------
    def _load(self) -> str:
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8"))
            return data.get("token", "") if data.get("base") == self.base else ""
        except (OSError, ValueError):
            return ""

    def _save(self) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.session_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"base": self.base, "token": self.token}, f)
        if sys.platform != "win32":
            os.chmod(self.session_path, 0o600)

    def login(self) -> str:
        if not self.base:
            raise NotConfigured()
        acc = self.account()
        if acc is None:
            raise NotConfigured()
        sid = self.http.post_json(f"{self.base}/v1/auth/challenge", {})["server_id"]
        self.http.post_json(ELY_JOIN, {"accessToken": acc.access_token, "selectedProfile": acc.uuid, "serverId": sid})
        r = self.http.post_json(f"{self.base}/v1/auth/verify", {"name": acc.name, "server_id": sid})
        self.token = r["token"]
        self._save()
        return r.get("name", acc.name)

    def _call(self, path: str, body: dict | None = None) -> dict:
        if not self.base:
            raise NotConfigured()
        if not self.token:
            self.login()
        for attempt in (0, 1):
            headers = {"Authorization": f"Bearer {self.token}"}
            try:
                if body is None:
                    return self.http.get_json(f"{self.base}{path}", headers=headers)
                return self.http.post_json(f"{self.base}{path}", body, headers=headers)
            except HttpError as e:
                if e.status != 401 or attempt == 1:
                    raise
                self.login()
        raise RuntimeError("unreachable")

    # ---------- api ----------
    def state(self) -> dict:
        return self._call("/v1/state")

    def presence(self, status: str, pack: str = "", server: str = "") -> dict:
        return self._call("/v1/presence", {"status": status, "pack": pack, "server": server})

    def request(self, name: str) -> dict:
        return self._call("/v1/friends/request", {"name": name})

    def accept(self, name: str) -> dict:
        return self._call("/v1/friends/accept", {"name": name})

    def decline(self, name: str) -> dict:
        return self._call("/v1/friends/decline", {"name": name})

    def remove(self, name: str) -> dict:
        return self._call("/v1/friends/remove", {"name": name})

    def invite(self, name: str, pack: str, server: str) -> dict:
        return self._call("/v1/invite", {"name": name, "pack": pack, "server": server})

    def dismiss(self, name: str) -> dict:
        return self._call("/v1/invite/dismiss", {"from": name})
