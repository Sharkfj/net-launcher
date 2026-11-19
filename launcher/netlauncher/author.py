"""Pack author tools: build an .mrpack from a game folder and publish it to GitHub."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from netlauncher import catalog
from netlauncher.catalog import Catalog, PackEntry
from netlauncher.modmeta import read_jar, sha1_file
from netlauncher.modrinth import Modrinth
from netlauncher.net import Http, HttpError
from netlauncher.pack import ManualFile, PackFile, PackIndex, write_mrpack

ALLOWED_LICENSES = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "lgpl-2.1", "lgpl-3.0", "gpl-3.0",
                    "mpl-2.0", "cc0-1.0", "isc", "unlicense"}
OVERRIDE_DIRS = ("config", "defaultconfigs", "resourcepacks", "shaderpacks", "pointblank")
OVERRIDE_FILES = ("options.txt",)
CONTENT_DIRS = {"mods": (".jar",), "resourcepacks": (".zip",), "shaderpacks": (".zip",), "pointblank": (".zip",)}
SIDES = {"required", "optional", "unsupported"}
GH_API = "https://api.github.com"
GH_UPLOADS = "https://uploads.github.com"

_TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                     ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r",
                      "s", "t", "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


@dataclass
class PackDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    index: PackIndex
    overrides: list[str]
    warnings: list[str]
    diff: PackDiff


def license_allowed(lic: str) -> bool:
    for part in re.split(r"\s+(?:OR|AND)\s+|[,/]", lic or ""):
        p = part.strip().lower()
        p = re.sub(r"-(only|or-later)$", "", p).rstrip("+")
        if p in ALLOWED_LICENSES:
            return True
    return False


def manual_page(name: str, display_url: str) -> str:
    """A file that is not on Modrinth: its Modrinth link is dead by definition, so point at CurseForge search."""
    if display_url and "modrinth.com" not in display_url:
        return display_url
    return "https://www.curseforge.com/minecraft/search?search=" + quote(name, safe="")


def _side(v: str) -> str:
    return v if v in SIDES else "required"


def _content_files(game_dir: Path) -> list[str]:
    out = []
    for d, exts in CONTENT_DIRS.items():
        folder = game_dir / d
        if folder.is_dir():
            out += sorted(f"{d}/{p.name}" for p in folder.iterdir() if p.is_file() and p.name.lower().endswith(exts))
    return out


def _slot(path: str, project: str) -> str:
    return project or path


def _diff(new: PackIndex, overrides: list[str], prev: PackIndex | None) -> PackDiff:
    def slots(files, extra):
        d = {_slot(f.path, f.project): f for f in files}
        for rel in extra:
            if rel.startswith("mods/"):
                d[rel] = None
        return d

    new_mods = [o for o in overrides if o.startswith("mods/")] + [m.path for m in new.manual]
    cur = slots(new.files, new_mods)
    old = slots(prev.files, [m.path for m in prev.manual]) if prev else {}
    name = lambda k, f: Path(f.path if f else k).name  # noqa: E731
    diff = PackDiff()
    for k, f in cur.items():
        if k not in old:
            diff.added.append(name(k, f))
        elif f and old[k] and f.sha1 != old[k].sha1:
            diff.updated.append(name(k, f))
    diff.removed = [name(k, f) for k, f in old.items() if k not in cur]
    for lst in (diff.added, diff.removed, diff.updated):
        lst.sort()
    return diff


def build(game_dir: Path, modrinth: Modrinth, name: str, version: str, mc_version: str, loader: str,
          loader_version: str, changelog: str, prev: PackIndex | None, cf=None) -> BuildResult:
    game_dir = Path(game_dir)
    content = _content_files(game_dir)
    hashes = {rel: sha1_file(game_dir / rel) for rel in content}
    found = modrinth.versions_by_hash(list(hashes.values()))
    projects = modrinth.projects(sorted({v.project_id for v in found.values()}))
    files: list[PackFile] = []
    manual: list[ManualFile] = []
    overrides: list[str] = []
    warnings: list[str] = []
    cf_hits: dict = {}
    if cf is not None:
        rest = [game_dir / rel for rel in content if hashes[rel] not in found]
        cf_hits = {p.relative_to(game_dir).as_posix(): hit for p, hit in cf.match_files(rest).items()}
    for rel in content:
        digest = hashes[rel]
        if rel in cf_hits:
            mod, f = cf_hits[rel]
            path = game_dir / rel
            if f.get("downloadUrl"):
                files.append(PackFile(rel, digest, hashlib.sha512(path.read_bytes()).hexdigest(), path.stat().st_size,
                                      [f["downloadUrl"]]))
            else:
                manual.append(ManualFile(rel, digest, mod.get("name", rel), cf.page(mod, f.get("id"))))
                warnings.append(f"{mod.get('name', rel)}: автор запретил перезалив, игроки скачают вручную")
            continue
        v = found.get(digest)
        if v:
            f = next((x for x in v.files if x.sha1 == digest), v.primary_file)
            proj = projects.get(v.project_id)
            client = _side(proj.client_side if proj else "")
            # singleplayer runs a server inside the client: server-only mods (worldgen, weather) are needed there too
            if client == "unsupported":
                client = "optional"
            files.append(PackFile(rel, digest, f.sha512, f.size or (game_dir / rel).stat().st_size, [f.url],
                                  client, _side(proj.server_side if proj else "")))
            continue
        if rel.startswith("mods/"):
            meta = read_jar(game_dir / rel)
            if meta and not license_allowed(meta.license):
                manual.append(ManualFile(rel, digest, meta.name, manual_page(meta.name, meta.display_url)))
                warnings.append(f"{meta.name}: закрытая лицензия, игроки скачают вручную")
                continue
        overrides.append(rel)
    for d in OVERRIDE_DIRS:
        folder = game_dir / d
        if folder.is_dir():
            for p in sorted(folder.rglob("*")):
                rel = p.relative_to(game_dir).as_posix()
                if p.is_file() and rel not in hashes:
                    overrides.append(rel)
    overrides += [f for f in OVERRIDE_FILES if (game_dir / f).is_file()]
    index = PackIndex(name, version, mc_version, loader, loader_version, files, manual,
                      list(prev.preserve) if prev else [], changelog)
    return BuildResult(index, sorted(set(overrides)), warnings, _diff(index, overrides, prev))


def write(result: BuildResult, game_dir: Path, dest_dir: Path, pack_id: str) -> Path:
    return write_mrpack(Path(dest_dir) / f"{pack_id}-{result.index.version}.mrpack", result.index, Path(game_dir),
                        result.overrides)


def new_pack_id(name: str, existing: set[str]) -> str:
    s = "".join(_TRANSLIT.get(ch, ch) for ch in name.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "pack"
    cand, n = s, 2
    while cand in existing:
        cand, n = f"{s}-{n}", n + 1
    return cand


def _headers(token: str, extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    h.update(extra or {})
    return h


def publish(http: Http, repo: str, token: str, entry: PackEntry, mrpack: Path) -> str:
    mrpack = Path(mrpack)
    rel = http.post_json(f"{GH_API}/repos/{repo}/releases",
                         {"tag_name": f"{entry.id}-v{entry.version}", "name": f"{entry.name} {entry.version}",
                          "body": entry.changelog, "make_latest": "false"}, headers=_headers(token))
    status, body = http.request(
        "POST", f"{GH_UPLOADS}/repos/{repo}/releases/{rel['id']}/assets?name={quote(mrpack.name)}",
        data=mrpack.read_bytes(), headers=_headers(token, {"Content-Type": "application/zip"}))
    asset = json.loads(body or b"{}")
    entry.mrpack_url = asset.get("browser_download_url", "")
    entry.mrpack_sha1 = sha1_file(mrpack)
    url = catalog.contents_url(repo)
    sha = None
    try:
        cur = http.get_json(url, headers=_headers(token))
        sha = cur.get("sha")
        cat = catalog.parse(json.loads(base64.b64decode(cur.get("content", "")).decode("utf-8")))
    except HttpError as e:
        if e.status != 404:
            raise
        cat = Catalog("", {}, [])
    for i, p in enumerate(cat.packs):
        if p.id == entry.id:
            cat.packs[i] = entry
            break
    else:
        cat.packs.append(entry)
    payload = {"message": f"{entry.name} {entry.version}",
               "content": base64.b64encode(json.dumps(catalog.to_json(cat), ensure_ascii=False,
                                                      indent=1).encode("utf-8")).decode()}
    if sha:
        payload["sha"] = sha
    http.request("PUT", url, data=json.dumps(payload).encode(), headers=_headers(token))
    return rel.get("html_url", "")

