"""Pack catalog: which packs exist, their latest versions and servers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from netlauncher.net import Http, HttpError, Offline

PACK_REPO = ""  # "<user>/<repo>", filled in once the GitHub repository exists
CATALOG_PATH = "catalog.json"


@dataclass
class PackEntry:
    id: str
    name: str
    description: str
    version: str
    mc_version: str
    loader: str
    loader_version: str
    mrpack_url: str
    mrpack_sha1: str
    changelog: str = ""
    server: str = ""
    cover_url: str = ""


@dataclass
class Catalog:
    launcher_version: str
    launcher_urls: dict[str, str]
    packs: list[PackEntry] = field(default_factory=list)

    def get(self, pack_id: str) -> PackEntry | None:
        return next((p for p in self.packs if p.id == pack_id), None)


_ENTRY_FIELDS = {f.name for f in fields(PackEntry)}


def parse(raw: dict) -> Catalog:
    launcher = raw.get("launcher") or {}
    packs = []
    for p in raw.get("packs") or []:
        try:
            packs.append(PackEntry(**{k: str(v) for k, v in p.items() if k in _ENTRY_FIELDS}))
        except TypeError:
            continue
    return Catalog(str(launcher.get("version", "")), dict(launcher.get("urls") or {}), packs)


def to_json(cat: Catalog) -> dict:
    return {"format": 1, "launcher": {"version": cat.launcher_version, "urls": cat.launcher_urls},
            "packs": [vars(p) for p in cat.packs]}


def contents_url(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/contents/{CATALOG_PATH}"


def fetch(http: Http, repo: str) -> Catalog | None:
    try:
        raw = http.get_json(contents_url(repo), headers={"Accept": "application/vnd.github.raw+json"})
    except (Offline, HttpError, ValueError):
        return None
    return parse(raw) if isinstance(raw, dict) else None


def resolve(http: Http) -> Catalog | None:
    override = os.environ.get("NET_LAUNCHER_CATALOG")
    if override:
        if override.startswith(("http://", "https://")):
            try:
                return parse(http.get_json(override))
            except (Offline, HttpError, ValueError):
                return None
        try:
            return parse(json.loads(Path(override).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None
    return fetch(http, PACK_REPO) if PACK_REPO else None


def _parts(v: str) -> list[int]:
    out = []
    for x in v.split("."):
        digits = "".join(ch for ch in x if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return out


def is_newer(a: str, b: str) -> bool:
    pa, pb = _parts(a), _parts(b)
    n = max(len(pa), len(pb))
    return pa + [0] * (n - len(pa)) > pb + [0] * (n - len(pb))


def updates(cat: Catalog | None, installed: dict[str, str]) -> dict[str, PackEntry]:
    if cat is None:
        return {}
    return {p.id: p for p in cat.packs if p.id in installed and is_newer(p.version, installed[p.id])}
