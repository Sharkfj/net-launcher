"""HTTP transport: JSON calls and verified downloads."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Protocol

import requests

from netlauncher import __version__

USER_AGENT = f"NETLauncher/{__version__}"
TIMEOUT = 30
CHUNK = 256 * 1024


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status}: {url}")
        self.status, self.url, self.body = status, url, body


class Offline(Exception):
    def __init__(self, url: str):
        super().__init__(f"Нет соединения: {url}")
        self.url = url


class HashMismatch(Exception):
    def __init__(self, path: Path):
        super().__init__(f"Файл повреждён при скачивании: {Path(path).name}")
        self.path = Path(path)


class Http(Protocol):
    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> Any: ...
    def post_json(self, url: str, body: Any, headers: dict | None = None) -> Any: ...
    def request(self, method: str, url: str, *, data: bytes | None = None,
                headers: dict | None = None) -> tuple[int, bytes]: ...
    def download(self, url: str, dest: Path, sha1: str | None = None, sha512: str | None = None,
                 progress: Callable[[int, int], None] | None = None) -> Path: ...


class RequestsHttp:
    def __init__(self, retries: int = 3, backoff: float = 0.8):
        self.retries, self.backoff = retries, backoff
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _send(self, method: str, url: str, **kw) -> requests.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self.session.request(method, url, timeout=TIMEOUT, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e
            else:
                if r.status_code < 500 or attempt == self.retries:
                    if r.status_code >= 400:
                        raise HttpError(r.status_code, url, r.text[:500])
                    return r
                last = HttpError(r.status_code, url)
            if attempt < self.retries:
                time.sleep(self.backoff * (2 ** attempt))
        if isinstance(last, HttpError):
            raise last
        raise Offline(url)

    def get_json(self, url, params=None, headers=None):
        return self._send("GET", url, params=params, headers=headers).json()

    def post_json(self, url, body, headers=None):
        r = self._send("POST", url, json=body, headers=headers)
        return r.json() if r.content else None

    def request(self, method, url, *, data=None, headers=None):
        r = self._send(method, url, data=data, headers=headers)
        return r.status_code, r.content

    def download(self, url, dest, sha1=None, sha512=None, progress=None):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        h1, h512 = hashlib.sha1(), hashlib.sha512()
        try:
            r = self._send("GET", url, stream=True)
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(part, "wb") as f:
                for chunk in r.iter_content(CHUNK):
                    f.write(chunk)
                    h1.update(chunk)
                    h512.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total or done)
        except requests.RequestException as e:
            part.unlink(missing_ok=True)
            raise Offline(url) from e
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        if (sha1 and h1.hexdigest() != sha1.lower()) or (sha512 and h512.hexdigest() != sha512.lower()):
            part.unlink(missing_ok=True)
            raise HashMismatch(dest)
        os.replace(part, dest)
        return dest
