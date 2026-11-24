""".mrpack pack format (+ net.json extension) and safe incremental updates."""

from __future__ import annotations

from netlauncher.i18n import t

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from netlauncher import snapshots
from netlauncher.modmeta import sha1_file
from netlauncher.net import HashMismatch, Http

INDEX = "modrinth.index.json"
EXT = "net.json"
OVERRIDE_PREFIXES = ("overrides/", "client-overrides/")
LOADER_KEYS = {"neoforge": "neoforge", "fabric": "fabric-loader", "forge": "forge", "quilt": "quilt-loader"}
PROTECTED_DIRS = ("saves/", "screenshots/")
ONLY_IF_MISSING = ("options.txt",)
STATE_FILE = Path(".net") / "pack-state.json"
DISABLED = ".disabled"
Progress = Callable[[str, int, int], None]


class UnsafePath(Exception):
    def __init__(self, path: str):
        super().__init__(t('Небезопасный путь в сборке: {path}', path=path))
        self.path = path


def safe_rel(p: str) -> str:
    q = p.replace("\\", "/")
    while q.startswith("./"):
        q = q[2:]
    if not q or q.startswith("/") or re.match(r"^[A-Za-z]:", q) or ".." in q.split("/"):
        raise UnsafePath(p)
    return q


@dataclass
class PackFile:
    path: str
    sha1: str
    sha512: str
    size: int
    urls: list[str]
    client: str = "required"
    server: str = "required"

    @property
    def project(self) -> str:
        for u in self.urls:
            m = re.search(r"/data/([A-Za-z0-9]+)/", u)
            if m:
                return m.group(1)
        return ""


@dataclass
class ManualFile:
    path: str
    sha1: str
    name: str
    page_url: str


@dataclass
class PackIndex:
    name: str
    version: str
    mc_version: str
    loader: str
    loader_version: str
    files: list[PackFile]
    manual: list[ManualFile] = field(default_factory=list)
    preserve: list[str] = field(default_factory=list)
    changelog: str = ""


def _index_json(idx: PackIndex) -> dict:
    deps = {"minecraft": idx.mc_version}
    if idx.loader:
        deps[LOADER_KEYS.get(idx.loader, idx.loader)] = idx.loader_version
    return {
        "formatVersion": 1, "game": "minecraft", "versionId": idx.version, "name": idx.name,
        "summary": idx.changelog.splitlines()[0] if idx.changelog else "",
        "files": [{"path": f.path, "hashes": {"sha1": f.sha1, "sha512": f.sha512},
                   "env": {"client": f.client, "server": f.server}, "downloads": f.urls, "fileSize": f.size}
                  for f in idx.files],
        "dependencies": deps,
    }


def _parse_index(raw: dict, ext: dict) -> PackIndex:
    deps = dict(raw.get("dependencies") or {})
    mc = deps.pop("minecraft", "")
    loader, lv = "", ""
    for name, key in LOADER_KEYS.items():
        if key in deps:
            loader, lv = name, deps[key]
            break
    files = []
    for f in raw.get("files") or []:
        env = f.get("env") or {}
        h = f.get("hashes") or {}
        files.append(PackFile(safe_rel(f["path"]), h.get("sha1", ""), h.get("sha512", ""),
                              int(f.get("fileSize") or 0), list(f.get("downloads") or []),
                              env.get("client", "required"), env.get("server", "required")))
    manual = [ManualFile(safe_rel(m["path"]), m["sha1"], m.get("name", ""), m.get("page_url", ""))
              for m in ext.get("manual") or []]
    preserve = [safe_rel(p) for p in ext.get("preserve") or []]
    return PackIndex(raw.get("name", ""), str(raw.get("versionId", "")), mc, loader, lv, files, manual, preserve,
                     ext.get("changelog", raw.get("summary", "")))


class MrPack:
    def __init__(self, path: Path, index: PackIndex, overrides: dict[str, str]):
        self.path, self.index, self._overrides = Path(path), index, overrides
        self._zip: zipfile.ZipFile | None = None

    @classmethod
    def open(cls, path: Path) -> "MrPack":
        with zipfile.ZipFile(path) as z:
            raw = json.loads(z.read(INDEX).decode("utf-8"))
            ext = json.loads(z.read(EXT).decode("utf-8")) if EXT in z.namelist() else {}
            overrides: dict[str, str] = {}
            for prefix in OVERRIDE_PREFIXES:  # client-overrides win
                for name in z.namelist():
                    if name.startswith(prefix) and not name.endswith("/"):
                        overrides[safe_rel(name[len(prefix):])] = name
        return cls(path, _parse_index(raw, ext), overrides)

    def override_paths(self) -> list[str]:
        return sorted(self._overrides)

    def read_override(self, rel: str) -> bytes:
        if self._zip is None:
            self._zip = zipfile.ZipFile(self.path)
        return self._zip.read(self._overrides[rel])

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def write_mrpack(dest: Path, index: PackIndex, overrides_root: Path, override_files: list[str]) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    ext = {"manual": [asdict(m) for m in index.manual], "preserve": index.preserve, "changelog": index.changelog}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(INDEX, json.dumps(_index_json(index), ensure_ascii=False, indent=1))
        z.writestr(EXT, json.dumps(ext, ensure_ascii=False, indent=1))
        for rel in override_files:
            z.write(Path(overrides_root) / rel, "overrides/" + safe_rel(rel))
    os.replace(tmp, dest)
    return dest


# ---------------- state ----------------
def load_state(game_dir: Path) -> dict | None:
    try:
        return json.loads((Path(game_dir) / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_state(game_dir: Path, state: dict) -> None:
    p = Path(game_dir) / STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


# ---------------- planning ----------------
@dataclass
class UpdatePlan:
    downloads: list[PackFile]
    overrides: list[str]
    remove: list[str]
    manual_missing: list[ManualFile]
    keep_disabled: set[str] = field(default_factory=set)


def _protected(rel: str) -> bool:
    return rel.startswith(PROTECTED_DIRS)


def _preserved(rel: str, preserve: list[str]) -> bool:
    return rel in ONLY_IF_MISSING or any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in preserve)


def _has(game_dir: Path, rel: str, sha1: str) -> bool:
    for cand in (game_dir / rel, game_dir / (rel + DISABLED)):
        if cand.is_file() and sha1_file(cand) == sha1:
            return True
    return False


def plan_update(pack: MrPack, game_dir: Path, state: dict | None) -> UpdatePlan:
    game_dir = Path(game_dir)
    idx = pack.index
    old: dict[str, dict] = (state or {}).get("files", {})
    disabled_projects = {v.get("project") for rel, v in old.items()
                         if v.get("project") and v.get("server") != "required"
                         and (game_dir / (rel + DISABLED)).exists() and not (game_dir / rel).exists()}
    downloads, keep_disabled = [], set()
    for f in idx.files:
        if f.client == "unsupported":
            continue
        if f.server != "required" and (f.project in disabled_projects
                                       or (game_dir / (f.path + DISABLED)).exists()):
            keep_disabled.add(f.path)
        if not _has(game_dir, f.path, f.sha1):
            downloads.append(f)
    overrides = []
    for rel in pack.override_paths():
        if _protected(rel):
            continue
        target = game_dir / rel
        if _preserved(rel, idx.preserve) and target.exists():
            continue
        if target.is_file() and sha1_file(target) == hashlib.sha1(pack.read_override(rel)).hexdigest():
            continue
        overrides.append(rel)
    new_paths = {f.path for f in idx.files if f.client != "unsupported"}
    new_paths |= set(pack.override_paths()) | {m.path for m in idx.manual}
    remove = sorted(rel for rel in old
                    if rel not in new_paths and not _protected(rel) and not _preserved(rel, idx.preserve)
                    and ((game_dir / rel).exists() or (game_dir / (rel + DISABLED)).exists()))
    manual_missing = [m for m in idx.manual if not _has(game_dir, m.path, m.sha1)]
    return UpdatePlan(downloads, overrides, remove, manual_missing, keep_disabled)


# ---------------- applying ----------------
def apply_update(plan: UpdatePlan, pack: MrPack, game_dir: Path, http: Http, cache_dir: Path,
                 snapshots_root: Path, progress: Progress | None = None) -> dict:
    game_dir, staging = Path(game_dir), Path(cache_dir) / "pack"
    idx = pack.index
    total = len(plan.downloads)
    staged: dict[str, Path] = {}
    # 1) download everything first: a failure here leaves the game folder untouched
    for n, f in enumerate(plan.downloads, 1):
        dest = staging / f.sha1
        if not (dest.is_file() and sha1_file(dest) == f.sha1):
            last: Exception | None = None
            for url in f.urls:
                try:
                    http.download(url, dest, sha1=f.sha1 or None, sha512=f.sha512 or None)
                    last = None
                    break
                except HashMismatch:
                    raise
                except Exception as e:  # try the next mirror
                    last = e
            if last is not None:
                raise last
        staged[f.path] = dest
        if progress:
            progress(Path(f.path).name, n, total)
    # 2) safety snapshot of the current state
    if (game_dir / "mods").is_dir():
        snapshots.create(snapshots_root, game_dir, t('Перед обновлением сборки до {version}', version=idx.version))
    # 3) apply
    game_dir.mkdir(parents=True, exist_ok=True)
    for rel in plan.remove:
        for cand in (game_dir / rel, game_dir / (rel + DISABLED)):
            if cand.is_file():
                cand.unlink()
    for rel in plan.overrides:
        target = game_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pack.read_override(rel))
    for f in plan.downloads:
        disabled = f.path in plan.keep_disabled
        target = game_dir / (f.path + DISABLED if disabled else f.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        for stale in (game_dir / f.path, game_dir / (f.path + DISABLED)):
            if stale.is_file() and stale != target:
                stale.unlink()
        shutil.copyfile(staged[f.path], target)
    # 4) record what the pack owns — last, so an interrupted run is redone next time
    files: dict[str, dict] = {}
    for f in idx.files:
        if f.client != "unsupported":
            files[f.path] = {"sha1": f.sha1, "client": f.client, "server": f.server, "project": f.project}
    for rel in pack.override_paths():
        target = game_dir / rel
        if _protected(rel) or not target.is_file():
            continue
        if _preserved(rel, idx.preserve) and rel not in plan.overrides:
            continue
        files[rel] = {"sha1": sha1_file(target), "client": "required", "server": "required", "project": ""}
    for m in idx.manual:
        if _has(game_dir, m.path, m.sha1):
            files[m.path] = {"sha1": m.sha1, "client": "required", "server": "required", "project": ""}
    state = {"version": idx.version, "name": idx.name, "mc_version": idx.mc_version, "loader": idx.loader,
             "loader_version": idx.loader_version, "files": files}
    save_state(game_dir, state)
    for p in staged.values():
        p.unlink(missing_ok=True)
    return state


def add_manual(pack_index: PackIndex, game_dir: Path, src_file: Path) -> ManualFile:
    digest = sha1_file(src_file)
    for m in pack_index.manual:
        if m.sha1 == digest:
            target = Path(game_dir) / m.path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_file, target)
            return m
    raise HashMismatch(Path(src_file))
