#!/usr/bin/env python3
""".NET Launcher friends service: friend requests, online status, invites.

Standard library only. Players prove who they are the way Minecraft servers do it: the launcher
"joins" a random server id at Ely.by, and this service asks Ely.by whether that player has joined.

Run:  python3 friends_server.py --port 8770 --db friends.db
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

ELY_HAS_JOINED = "https://authserver.ely.by/session/hasJoined"
ONLINE_SECONDS = 60
CHALLENGE_SECONDS = 300
MAX_BODY = 16 * 1024
NAME_RE = re.compile(r"^[A-Za-z0-9_]{2,16}$")
STATUSES = {"launcher", "playing"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY COLLATE NOCASE, uuid TEXT, last_seen REAL DEFAULT 0,
                                  status TEXT DEFAULT '', pack TEXT DEFAULT '', server TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, name TEXT, created REAL);
CREATE TABLE IF NOT EXISTS challenges (server_id TEXT PRIMARY KEY, created REAL);
CREATE TABLE IF NOT EXISTS friends (a TEXT COLLATE NOCASE, b TEXT COLLATE NOCASE, PRIMARY KEY (a, b));
CREATE TABLE IF NOT EXISTS requests (src TEXT COLLATE NOCASE, dst TEXT COLLATE NOCASE, created REAL,
                                     PRIMARY KEY (src, dst));
CREATE TABLE IF NOT EXISTS invites (src TEXT COLLATE NOCASE, dst TEXT COLLATE NOCASE, pack TEXT, server TEXT,
                                    created REAL, PRIMARY KEY (src, dst));
"""


def ely_verifier(name: str, server_id: str) -> dict | None:
    q = urllib.parse.urlencode({"username": name, "serverId": server_id})
    try:
        with urllib.request.urlopen(f"{ELY_HAS_JOINED}?{q}", timeout=10) as r:
            if r.status != 200:
                return None
            data = json.loads(r.read() or b"null")
    except Exception:  # noqa: BLE001 - any failure means "not verified"
        return None
    return data if isinstance(data, dict) and data.get("name") else None


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def q(self, sql: str, args=()) -> list[tuple]:
        with self.lock, self.db:
            return self.db.execute(sql, args).fetchall()


class Api:
    def __init__(self, store: Store, verifier: Callable[[str, str], dict | None]):
        self.s, self.verify = store, verifier

    # ---------- helpers ----------
    @staticmethod
    def _name(body: dict, key: str = "name") -> str:
        n = str(body.get(key, ""))
        if not NAME_RE.match(n):
            raise ApiError(400, "bad name")
        return n

    def _canon(self, name: str) -> str:
        row = self.s.q("SELECT name FROM users WHERE name = ?", (name,))
        return row[0][0] if row else name

    def _are_friends(self, a: str, b: str) -> bool:
        return bool(self.s.q("SELECT 1 FROM friends WHERE a = ? AND b = ?", (a, b)))

    def user_for(self, token: str | None) -> str:
        if not token:
            raise ApiError(401, "no session")
        row = self.s.q("SELECT name FROM sessions WHERE token = ?", (token,))
        if not row:
            raise ApiError(401, "no session")
        return row[0][0]

    # ---------- auth ----------
    def challenge(self, body: dict) -> dict:
        sid = secrets.token_hex(16)
        now = time.time()
        self.s.q("DELETE FROM challenges WHERE created < ?", (now - CHALLENGE_SECONDS,))
        self.s.q("INSERT INTO challenges VALUES (?, ?)", (sid, now))
        return {"server_id": sid}

    def verify_login(self, body: dict) -> dict:
        name = self._name(body)
        sid = str(body.get("server_id", ""))
        row = self.s.q("SELECT created FROM challenges WHERE server_id = ?", (sid,))
        if not row or time.time() - row[0][0] > CHALLENGE_SECONDS:
            raise ApiError(401, "challenge expired")
        self.s.q("DELETE FROM challenges WHERE server_id = ?", (sid,))
        prof = self.verify(name, sid)
        if not prof:
            raise ApiError(401, "ely.by did not confirm the player")
        real = prof["name"]
        self.s.q("INSERT INTO users (name, uuid) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET uuid = excluded.uuid",
                 (real, prof.get("id", "")))
        token = secrets.token_urlsafe(32)
        self.s.q("INSERT INTO sessions VALUES (?, ?, ?)", (token, real, time.time()))
        return {"token": token, "name": real}

    # ---------- state ----------
    def state(self, me: str) -> dict:
        now = time.time()
        friends = []
        for name, last, status, pack, server in self.s.q(
                "SELECT u.name, u.last_seen, u.status, u.pack, u.server FROM friends f "
                "JOIN users u ON u.name = f.b WHERE f.a = ? ORDER BY u.name COLLATE NOCASE", (me,)):
            online = now - (last or 0) < ONLINE_SECONDS
            friends.append({"name": name, "online": online, "status": status if online else "",
                            "pack": pack if online else "", "server": server if online else "",
                            "last_seen": last or 0})
        incoming = [r[0] for r in self.s.q("SELECT src FROM requests WHERE dst = ? ORDER BY created", (me,))]
        outgoing = [self._canon(r[0]) for r in self.s.q("SELECT dst FROM requests WHERE src = ? ORDER BY created",
                                                        (me,))]
        invites = [{"from": s, "pack": p, "server": sv, "created": c} for s, p, sv, c in
                   self.s.q("SELECT src, pack, server, created FROM invites WHERE dst = ? ORDER BY created", (me,))]
        return {"me": me, "friends": friends, "incoming": incoming, "outgoing": outgoing, "invites": invites}

    def presence(self, me: str, body: dict) -> dict:
        status = str(body.get("status", "launcher"))
        if status not in STATUSES:
            raise ApiError(400, "bad status")
        self.s.q("UPDATE users SET last_seen = ?, status = ?, pack = ?, server = ? WHERE name = ?",
                 (time.time(), status, str(body.get("pack", ""))[:64], str(body.get("server", ""))[:128], me))
        return self.state(me)

    # ---------- friends ----------
    def request(self, me: str, body: dict) -> dict:
        other = self._canon(self._name(body))
        if other.lower() == me.lower():
            raise ApiError(400, "that is you")
        if self._are_friends(me, other):
            return self.state(me)
        if self.s.q("SELECT 1 FROM requests WHERE src = ? AND dst = ?", (other, me)):
            return self.accept(me, {"name": other})
        self.s.q("INSERT OR IGNORE INTO requests VALUES (?, ?, ?)", (me, other, time.time()))
        return self.state(me)

    def accept(self, me: str, body: dict) -> dict:
        other = self._canon(self._name(body))
        if not self.s.q("SELECT 1 FROM requests WHERE src = ? AND dst = ?", (other, me)):
            raise ApiError(404, "no such request")
        self.s.q("DELETE FROM requests WHERE (src = ? AND dst = ?) OR (src = ? AND dst = ?)", (other, me, me, other))
        self.s.q("INSERT OR IGNORE INTO friends VALUES (?, ?)", (me, other))
        self.s.q("INSERT OR IGNORE INTO friends VALUES (?, ?)", (other, me))
        return self.state(me)

    def decline(self, me: str, body: dict) -> dict:
        other = self._name(body)
        self.s.q("DELETE FROM requests WHERE src = ? AND dst = ?", (other, me))
        return self.state(me)

    def remove(self, me: str, body: dict) -> dict:
        other = self._name(body)
        self.s.q("DELETE FROM friends WHERE (a = ? AND b = ?) OR (a = ? AND b = ?)", (me, other, other, me))
        self.s.q("DELETE FROM invites WHERE (src = ? AND dst = ?) OR (src = ? AND dst = ?)", (me, other, other, me))
        return self.state(me)

    def invite(self, me: str, body: dict) -> dict:
        other = self._canon(self._name(body))
        if not self._are_friends(me, other):
            raise ApiError(403, "not friends")
        self.s.q("INSERT OR REPLACE INTO invites VALUES (?, ?, ?, ?, ?)",
                 (me, other, str(body.get("pack", ""))[:64], str(body.get("server", ""))[:128], time.time()))
        return self.state(me)

    def dismiss(self, me: str, body: dict) -> dict:
        self.s.q("DELETE FROM invites WHERE src = ? AND dst = ?", (self._name(body, "from"), me))
        return self.state(me)


ROUTES = {
    ("POST", "/v1/auth/challenge"): ("challenge", False),
    ("POST", "/v1/auth/verify"): ("verify_login", False),
    ("GET", "/v1/state"): ("state", True),
    ("POST", "/v1/presence"): ("presence", True),
    ("POST", "/v1/friends/request"): ("request", True),
    ("POST", "/v1/friends/accept"): ("accept", True),
    ("POST", "/v1/friends/decline"): ("decline", True),
    ("POST", "/v1/friends/remove"): ("remove", True),
    ("POST", "/v1/invite"): ("invite", True),
    ("POST", "/v1/invite/dismiss"): ("dismiss", True),
}


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NETFriends/1"

        def log_message(self, fmt, *args):  # keep stdout quiet
            pass

        def _send(self, status: int, payload) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method: str) -> None:
            route = ROUTES.get((method, urllib.parse.urlparse(self.path).path))
            if route is None:
                self._send(404, {"error": "not found"})
                return
            name, needs_auth = route
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    raise ApiError(413, "too large")
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else {}
                if not isinstance(body, dict):
                    raise ApiError(400, "bad json")
                fn = getattr(api, name)
                if needs_auth:
                    auth = self.headers.get("Authorization", "")
                    me = api.user_for(auth[7:] if auth.startswith("Bearer ") else None)
                    result = fn(me) if name == "state" else fn(me, body)
                else:
                    result = fn(body)
                self._send(200, result)
            except ApiError as e:
                self._send(e.status, {"error": e.message})
            except (ValueError, json.JSONDecodeError):
                self._send(400, {"error": "bad json"})

        def do_GET(self):  # noqa: N802
            self._handle("GET")

        def do_POST(self):  # noqa: N802
            self._handle("POST")

    return Handler


def make_server(host: str, port: int, db_path: Path, verifier=ely_verifier) -> ThreadingHTTPServer:
    api = Api(Store(Path(db_path)), verifier)
    return ThreadingHTTPServer((host, port), make_handler(api))


def main() -> None:
    ap = argparse.ArgumentParser(description=".NET Launcher friends service")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--db", default="friends.db")
    a = ap.parse_args()
    srv = make_server(a.host, a.port, Path(a.db))
    print(f"friends service on {a.host}:{a.port}, db {a.db}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
