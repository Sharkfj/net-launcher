"""Check the files of an official pack against what the launcher installed, and put them back.

Only mods/, resourcepacks/ and shaderpacks/ are checked. Shader settings (*.txt), hidden folders that mods
make for themselves (mods/.connector) and everything else in the game folder stay the player's.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from netlauncher.net import Http
from netlauncher.pack import DISABLED, MrPack, apply_update, load_state, plan_update
from netlauncher.modmeta import sha1_file

DIRS = ("mods", "resourcepacks", "shaderpacks")
CACHE = Path(".net") / "integrity.json"
REMOVED = Path(".net") / "removed"


class NoPackFile(Exception):
    """The pack's .mrpack is not cached and there is no link to download it."""


class NeedsInternet(Exception):
    """Files are missing or changed and can only come back from the internet."""


class NotRepaired(Exception):
    def __init__(self, report: "Report"):
        super().__init__(", ".join(report.missing + report.changed))
        self.report = report


@dataclass
class Report:
    missing: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.changed or self.extra)


def _hasher(game_dir: Path):
    path = game_dir / CACHE
    try:
        known = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    fresh: dict[str, list] = {}

    def sha1(rel: str, p: Path) -> str:
        st = p.stat()
        hit = known.get(rel)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            fresh[rel] = hit
            return hit[2]
        h = sha1_file(p)
        fresh[rel] = [st.st_size, st.st_mtime_ns, h]
        return h

    def save():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fresh), encoding="utf-8")
    return sha1, save


def _ignored(rel: str) -> bool:
    parts = rel.split("/")
    return any(p.startswith(".") for p in parts) or (parts[0] == "shaderpacks" and rel.endswith(".txt"))


def check(game_dir: Path, state: dict | None) -> Report:
    game_dir = Path(game_dir)
    owned = {rel: v for rel, v in (state or {}).get("files", {}).items() if rel.split("/")[0] in DIRS}
    sha1, save = _hasher(game_dir)
    r = Report()
    for rel, v in sorted(owned.items()):
        on, off = game_dir / rel, game_dir / (rel + DISABLED)
        p = on if on.is_file() else off if off.is_file() else None
        if p is None:
            r.missing.append(rel)
        elif sha1(rel, p) != v.get("sha1"):
            r.changed.append(rel)
    owned_dirs = {"/".join(rel.split("/")[:2]) for rel in owned if rel.count("/") >= 2}
    for top in DIRS:
        d = game_dir / top
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            rel = f"{top}/{entry.name}"
            if _ignored(rel):
                continue
            if entry.is_dir():
                if top != "mods" and rel not in owned_dirs:
                    r.extra.append(rel)
                continue
            base = rel[: -len(DISABLED)] if rel.endswith(DISABLED) else rel
            if base not in owned:
                r.extra.append(rel)
    save()
    return r


def repair(report: Report, lay, lp, http: Http, progress, mrpack_url: str = "") -> Report:
    """Move extra files to .net/removed/<time>/, bring missing and changed ones back from the pack file.

    Returns what is still wrong afterwards (normally nothing)."""
    gd = lay.instances / lp.id
    if report.extra:
        dest = gd / REMOVED / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        for rel in report.extra:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(gd / rel), str(target))
    if report.missing or report.changed:
        mp = lay.cache / "packs" / f"{lp.id}-{lp.version}.mrpack"
        if not mp.is_file():
            if not mrpack_url:
                raise NoPackFile(lp.id)
            http.download(mrpack_url, mp)
        with MrPack.open(mp) as pack:
            state = load_state(gd)
            apply_update(plan_update(pack, gd, state), pack, gd, http, lay.cache, lay.snapshots / lp.id, progress)
    return check(gd, load_state(gd))
