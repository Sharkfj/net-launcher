"""Minimal Modrinth API v2 client."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from netlauncher.net import Http

API = "https://api.modrinth.com/v2"


@dataclass
class MrFile:
    url: str
    filename: str
    sha1: str
    sha512: str
    size: int
    primary: bool


@dataclass
class MrVersion:
    id: str
    project_id: str
    version_number: str
    version_type: str
    game_versions: list[str]
    loaders: list[str]
    files: list[MrFile]
    required_deps: list[str]
    date: str

    @property
    def primary_file(self) -> MrFile:
        return next((f for f in self.files if f.primary), self.files[0])


@dataclass
class MrProject:
    id: str
    slug: str
    title: str
    description: str
    downloads: int
    icon_url: str
    project_type: str
    client_side: str
    server_side: str
    categories: list[str] = field(default_factory=list)


def _file(d: dict) -> MrFile:
    h = d.get("hashes") or {}
    return MrFile(d["url"], d["filename"], h.get("sha1", ""), h.get("sha512", ""), int(d.get("size") or 0),
                  bool(d.get("primary")))


def _version(d: dict) -> MrVersion:
    deps = [x["project_id"] for x in d.get("dependencies") or []
            if x.get("dependency_type") == "required" and x.get("project_id")]
    return MrVersion(d["id"], d["project_id"], d.get("version_number", ""), d.get("version_type", "release"),
                     list(d.get("game_versions") or []), list(d.get("loaders") or []),
                     [_file(f) for f in d.get("files") or []], deps, d.get("date_published", ""))


def _project(d: dict) -> MrProject:
    return MrProject(d.get("project_id") or d["id"], d.get("slug", ""), d.get("title", ""),
                     d.get("description", ""), int(d.get("downloads") or 0), d.get("icon_url") or "",
                     d.get("project_type", ""), d.get("client_side", "unknown"), d.get("server_side", "unknown"),
                     list(d.get("categories") or []))


def search_loader(kind: str, instance_loader: str) -> str | None:
    return {"mod": instance_loader, "shader": "iris"}.get(kind)


class Modrinth:
    def __init__(self, http: Http):
        self.http = http

    def search(self, query: str, project_type: str, game_version: str, loader: str | None,
               offset: int = 0, limit: int = 20) -> list[MrProject]:
        facets = [["versions:" + game_version], ["project_type:" + project_type]]
        if loader:
            facets.append(["categories:" + loader])
        params = {"query": query, "facets": json.dumps(facets), "offset": offset, "limit": limit,
                  "index": "relevance" if query else "downloads"}
        return [_project(h) for h in self.http.get_json(f"{API}/search", params=params).get("hits", [])]

    def project(self, id_or_slug: str) -> MrProject:
        return _project(self.http.get_json(f"{API}/project/{id_or_slug}"))

    def projects(self, ids: list[str]) -> dict[str, MrProject]:
        if not ids:
            return {}
        out = {}
        for i in range(0, len(ids), 100):
            for d in self.http.get_json(f"{API}/projects", params={"ids": json.dumps(ids[i:i + 100])}):
                p = _project(d)
                out[p.id] = p
        return out

    def versions(self, project: str, game_version: str, loader: str | None) -> list[MrVersion]:
        params = {"game_versions": json.dumps([game_version])}
        if loader:
            params["loaders"] = json.dumps([loader])
        vs = [_version(v) for v in self.http.get_json(f"{API}/project/{project}/version", params=params)]
        return sorted(vs, key=lambda v: v.date, reverse=True)

    def best_version(self, project: str, game_version: str, loader: str | None) -> MrVersion | None:
        vs = [v for v in self.versions(project, game_version, loader) if v.files]
        return next((v for v in vs if v.version_type == "release"), vs[0] if vs else None)

    def versions_by_hash(self, sha1s: list[str]) -> dict[str, MrVersion]:
        if not sha1s:
            return {}
        r = self.http.post_json(f"{API}/version_files", {"hashes": list(sha1s), "algorithm": "sha1"}) or {}
        return {h: _version(v) for h, v in r.items()}

    def latest_by_hash(self, sha1s: list[str], game_version: str, loader: str | None) -> dict[str, MrVersion]:
        if not sha1s:
            return {}
        body = {"hashes": list(sha1s), "algorithm": "sha1", "game_versions": [game_version]}
        if loader:
            body["loaders"] = [loader]
        r = self.http.post_json(f"{API}/version_files/update", body) or {}
        return {h: _version(v) for h, v in r.items()}
