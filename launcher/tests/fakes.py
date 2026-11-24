"""Test doubles shared by the test-suite."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from netlauncher.net import HashMismatch, HttpError, Offline


@dataclass
class Call:
    method: str
    url: str
    params: dict | None = None
    body: Any = None
    headers: dict | None = None


@dataclass
class FakeHttp:
    """Routes are keyed by exact URL; a value may be data or a callable(call) -> data.
    A route value that is an HttpError instance is raised."""

    routes: dict[str, Any] = field(default_factory=dict)
    downloads: dict[str, bytes] = field(default_factory=dict)
    offline: bool = False
    calls: list[Call] = field(default_factory=list)

    def _answer(self, call: Call) -> Any:
        self.calls.append(call)
        if self.offline:
            raise Offline(call.url)
        key = (call.method, call.url) if (call.method, call.url) in self.routes else call.url
        if key not in self.routes:
            raise HttpError(404, call.url)
        value = self.routes[key]
        if callable(value):
            value = value(call)
        if isinstance(value, Exception):
            raise value
        return value

    def get_json(self, url, params=None, headers=None):
        return self._answer(Call("GET", url, params=params, headers=headers))

    def post_json(self, url, body, headers=None):
        return self._answer(Call("POST", url, body=body, headers=headers))

    def request(self, method, url, *, data=None, headers=None):
        value = self._answer(Call(method, url, body=data, headers=headers))
        if isinstance(value, tuple):
            return value
        if isinstance(value, (dict, list)):
            return 200, json.dumps(value).encode()
        return 200, value if isinstance(value, bytes) else b""

    def download(self, url, dest: Path, sha1=None, sha512=None, progress: Callable | None = None, *, headers=None, sha256=None):
        self.calls.append(Call("DOWNLOAD", url, headers=headers))
        if self.offline:
            raise Offline(url)
        if url not in self.downloads:
            raise HttpError(404, url)
        data = self.downloads[url]
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if sha1 and hashlib.sha1(data).hexdigest() != sha1:
            raise HashMismatch(dest)
        if sha512 and hashlib.sha512(data).hexdigest() != sha512:
            raise HashMismatch(dest)
        if sha256 and hashlib.sha256(data).hexdigest() != sha256:
            raise HashMismatch(dest)
        dest.write_bytes(data)
        if progress:
            progress(len(data), len(data))
        return dest


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha512(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()
