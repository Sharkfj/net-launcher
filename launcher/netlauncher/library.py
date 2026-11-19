"""Installed mods / resource packs / shader packs: scan, toggle, install, update."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from netlauncher import snapshots
from netlauncher.modmeta import JarMeta, read_jar, sha1_file
from netlauncher.modrinth import Modrinth, MrProject, MrVersion, search_loader
from netlauncher.net import Http

Kind = Literal["mod", "resourcepack", "shader"]
FOLDERS: dict[str, str] = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
EXTS: dict[str, tuple[str, ...]] = {"mod": (".jar",), "resourcepack": (".zip",), "shader": (".zip",)}
DISABLED = ".disabled"
Progress = Callable[[str, int, int], None]


class Locked(Exception):
    def __init__(self, item: "Item"):
        super().__init__(f"{item.name}: нужен на сервере, выключить нельзя")
        self.item = item


class AlreadyInstalled(Exception):
    def __init__(self, name: str):
        super().__init__(f"{name} уже установлен")
        self.name = name


class NotAvailable(Exception):
    def __init__(self, name: str):
        super().__init__(f"{name}: нет версии для этой сборки")
        self.name = name


@dataclass
class Item:
    kind: str
    path: Path
    name: str
    version: str
    enabled: bool
    sha1: str
    meta: JarMeta | None
    from_pack: bool = False
    locked: bool = False

    @property
    def base_name(self) -> str:
        n = self.path.name
        return n[: -len(DISABLED)] if n.endswith(DISABLED) else n


@dataclass
class InstallPlan:
    items: list[tuple[MrProject, MrVersion]]
    skipped: list[str] = field(default_factory=list)


@dataclass
class Update:
    item: Item
    version: MrVersion


class Library:
    def __init__(self, game_dir: Path, snapshots_root: Path, modrinth: Modrinth, http: Http, cache_dir: Path,
                 game_version: str, loader: str, pack_state: dict[str, dict] | None = None):
        self.game_dir, self.snapshots_root = Path(game_dir), Path(snapshots_root)
        self.mr, self.http, self.cache_dir = modrinth, http, Path(cache_dir)
        self.game_version, self.loader = game_version, loader
        self.pack_state = pack_state or {}

    # ---------- scanning ----------
    def folder(self, kind: Kind) -> Path:
        return self.game_dir / FOLDERS[kind]

    def _item(self, kind: str, path: Path) -> Item:
        enabled = not path.name.endswith(DISABLED)
        base = path.name[: -len(DISABLED)] if not enabled else path.name
        meta = read_jar(path) if kind == "mod" else None
        name = meta.name if meta else Path(base).stem
        rel = f"{FOLDERS[kind]}/{base}"
        st = self.pack_state.get(rel)
        from_pack = st is not None
        locked = from_pack and st.get("server") == "required"
        return Item(kind, path, name, meta.version if meta else "", enabled, sha1_file(path), meta,
                    from_pack, locked)

    def scan(self, kind: Kind) -> list[Item]:
        d = self.folder(kind)
        if not d.is_dir():
            return []
        items = []
        for p in d.iterdir():
            if not p.is_file():
                continue
            base = p.name[: -len(DISABLED)] if p.name.endswith(DISABLED) else p.name
            if base.lower().endswith(EXTS[kind]):
                items.append(self._item(kind, p))
        return sorted(items, key=lambda i: i.name.lower())

    def _snapshot(self, reason: str) -> None:
        snapshots.create(self.snapshots_root, self.game_dir, reason)

    # ---------- toggle / remove ----------
    def set_enabled(self, item: Item, on: bool) -> Item:
        if item.enabled == on:
            return item
        if item.locked and not on:
            raise Locked(item)
        self._snapshot(("Включение: " if on else "Выключение: ") + item.name)
        target = item.path.with_name(item.base_name if on else item.base_name + DISABLED)
        os.replace(item.path, target)
        return self._item(item.kind, target)

    def remove(self, item: Item) -> None:
        if item.locked:
            raise Locked(item)
        self._snapshot("Удаление: " + item.name)
        item.path.unlink(missing_ok=True)

    # ---------- install ----------
    def _installed_projects(self, kind: Kind) -> set[str]:
        hashes = [i.sha1 for i in self.scan(kind)]
        return {v.project_id for v in self.mr.versions_by_hash(hashes).values()}

    def _installed_mod_ids(self) -> set[str]:
        ids: set[str] = set()
        for i in self.scan("mod"):
            if i.meta:
                ids.update(i.meta.mod_ids)
                ids.update(i.meta.nested_ids)
        return ids

    def plan_install(self, project_id: str, kind: Kind) -> InstallPlan:
        present = self._installed_projects(kind)
        loader = search_loader(kind, self.loader)
        if project_id in present:
            p = self.mr.projects([project_id]).get(project_id)
            raise AlreadyInstalled(p.title if p else project_id)
        chosen: list[tuple[str, MrVersion]] = []
        skipped: list[str] = []
        seen: set[str] = set()
        queue = [project_id]
        while queue:
            pid = queue.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            if pid in present:
                skipped.append(pid)
                continue
            v = self.mr.best_version(pid, self.game_version, loader)
            if v is None:
                raise NotAvailable(pid)
            chosen.append((pid, v))
            queue.extend(v.required_deps)
        projects = self.mr.projects([pid for pid, _ in chosen] + skipped)
        items = [(projects[pid], v) for pid, v in chosen if pid in projects]
        skipped_names = [projects[pid].slug if pid in projects else pid for pid in skipped]
        return InstallPlan(items, skipped_names)

    def _fetch(self, v: MrVersion, progress: Progress | None, label: str) -> Path:
        f = v.primary_file
        dest = self.cache_dir / "downloads" / f.filename
        cb = (lambda d, t: progress(label, d, t)) if progress else None
        return self.http.download(f.url, dest, sha1=f.sha1 or None, sha512=f.sha512 or None, progress=cb)

    def install(self, plan: InstallPlan, kind: Kind, progress: Progress | None = None) -> list[Item]:
        if not plan.items:
            return []
        self._snapshot("Установка: " + plan.items[0][0].title)
        folder = self.folder(kind)
        folder.mkdir(parents=True, exist_ok=True)
        existing_ids = self._installed_mod_ids() if kind == "mod" else set()
        out = []
        for idx, (proj, v) in enumerate(plan.items):
            tmp = self._fetch(v, progress, proj.title)
            if kind == "mod" and idx > 0:
                meta = read_jar(tmp)
                if meta and meta.mod_ids and meta.mod_ids[0] in existing_ids:
                    tmp.unlink(missing_ok=True)
                    plan.skipped.append(proj.slug)
                    continue
            target = folder / v.primary_file.filename
            shutil.move(str(tmp), target)
            item = self._item(kind, target)
            if item.meta:
                existing_ids.update(item.meta.mod_ids + item.meta.nested_ids)
            out.append(item)
        return out

    # ---------- updates ----------
    def check_updates(self, kind: Kind) -> list[Update]:
        items = [i for i in self.scan(kind) if not i.from_pack]
        if not items:
            return []
        hashes = [i.sha1 for i in items]
        current = self.mr.versions_by_hash(hashes)
        latest = self.mr.latest_by_hash(hashes, self.game_version, search_loader(kind, self.loader))
        out = []
        for i in items:
            new = latest.get(i.sha1)
            if not new or not new.files or new.primary_file.sha1 == i.sha1:
                continue
            cur = current.get(i.sha1)
            if cur and cur.id == new.id:
                continue
            if new.version_type != "release" and (cur is None or cur.version_type == "release"):
                continue
            out.append(Update(i, new))
        return out

    def apply_updates(self, updates: list[Update], progress: Progress | None = None) -> list[Item]:
        if not updates:
            return []
        self._snapshot(f"Обновление ({len(updates)})")
        out = []
        for up in updates:
            tmp = self._fetch(up.version, progress, up.item.name)
            name = up.version.primary_file.filename + ("" if up.item.enabled else DISABLED)
            target = up.item.path.with_name(name)
            if target != up.item.path:
                up.item.path.unlink(missing_ok=True)
            shutil.move(str(tmp), target)
            out.append(self._item(up.item.kind, target))
        return out
