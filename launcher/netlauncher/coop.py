"""e4mc compatibility, per-pack invitations and the current game's log cursor."""

import os
import re
from pathlib import Path

from netlauncher import localpacks
from netlauncher.i18n import t
from netlauncher.library import Library, NotAvailable
from netlauncher.modmeta import read_jar, sha1_file
from netlauncher.pack import load_state

PROJECT = "qANg5Jrr"
MOD_IDS = {"e4mc_minecraft", "e4mc"}
LOADERS = {"fabric", "quilt", "forge", "neoforge"}
OPT_IN = Path(".net") / "invite-friends"
DOMAIN = re.compile(
    r"^\[[^\]]+\] \[[^\]]+/INFO\](?: \[e4mc(?:_minecraft)?/[^\]]*\])?: Domain assigned: "
    r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+e4mc\.link)$", re.IGNORECASE
)


def source_id(lay, pack):
    try:
        original = (localpacks.game_dir(lay, pack.id) / ".net" / "shared-id").read_text(encoding="utf-8").strip()
    except OSError:
        original = ""
    return original or pack.id


def invited_pack(lay, name, pack_id="", version=""):
    packs = localpacks.list_installed(lay)
    if pack_id:
        return next((p for p in packs if source_id(lay, p) == pack_id and
                     (not version or p.version == version) and p.name == name), None)
    return next((p for p in packs if p.name == name), None)


def bundled(ctx, pack):
    return pack.official or bool(ctx.catalog and ctx.catalog.get(pack.id))


def _mod(game_dir, official, pattern="*.jar"):
    owned = (load_state(game_dir) or {}).get("files", {}) if official else {}
    for p in sorted((game_dir / "mods").glob(pattern), key=lambda p: "e4mc" not in p.name.lower()):
        rel = "mods/" + p.name
        if official and rel not in owned:
            continue
        meta = read_jar(p)
        if meta and MOD_IDS.intersection(meta.mod_ids):
            if not official or sha1_file(p) == owned[rel].get("sha1"):
                return p
    return None


def available(ctx, pack):
    if pack.loader not in LOADERS:
        return False
    official = bundled(ctx, pack)
    gd = localpacks.game_dir(ctx.lay, pack.id)
    if _mod(gd, official):
        return True
    return not official and ctx.modrinth.best_version(PROJECT, pack.mc_version, pack.loader) is not None


def set_enabled(ctx, pack, enabled, progress):
    gd = localpacks.game_dir(ctx.lay, pack.id)
    marker = gd / OPT_IN
    if not enabled:
        marker.unlink(missing_ok=True)
        return
    if not (gd / localpacks.PACK_FILE).is_file() or pack.loader not in LOADERS:
        raise NotAvailable("e4mc")
    official = bundled(ctx, pack)
    if not _mod(gd, official):
        if official:
            raise NotAvailable("e4mc")
        lib = Library(gd, ctx.lay.snapshots / pack.id, ctx.modrinth, ctx.http, ctx.lay.cache,
                      pack.mc_version, pack.loader)
        disabled = _mod(gd, False, "*.jar.disabled")
        if disabled:
            checksum = sha1_file(disabled)
            version = ctx.modrinth.versions_by_hash([checksum]).get(checksum)
            if (version is None or version.project_id != PROJECT or pack.mc_version not in version.game_versions
                    or pack.loader not in version.loaders):
                raise NotAvailable("e4mc")
            item = next(i for i in lib.scan("mod") if i.path == disabled)
            lib.set_enabled(item, True)
        else:
            plan = lib.plan_install(PROJECT, "mod")
            lib.install(plan, "mod", progress)
        if not _mod(gd, False):
            raise NotAvailable("e4mc")
    marker.touch()


def assigned_domain(line):
    match = DOMAIN.fullmatch(line)
    return match[1].lower() if match else None


def invite_friends(client, name, pack_id, version, server):
    state = client.presence("playing", name, server, pack_id=pack_id, pack_version=version)
    errors = []
    for friend in state.get("friends", []):
        try:
            client.invite(friend["name"], name, server, pack_id=pack_id, pack_version=version)
        except Exception as exc:
            errors.append((friend["name"], str(exc)))
    if errors:
        names = ", ".join(name for name, _ in errors)
        raise RuntimeError(t('Не удалось пригласить: {names}', names=names))


class SessionLog:
    """Read complete lines since launch, including after Minecraft rotates or truncates latest.log."""

    def __init__(self, path):
        self.path = Path(path)
        self.offset, self.identity, self.tail = 0, None, b""
        try:
            with self.path.open("rb") as f:
                self.offset = f.seek(0, 2)
                self._remember(f)
        except OSError:
            pass

    def _remember(self, f):
        stat = os.fstat(f.fileno())
        self.identity = stat.st_dev, stat.st_ino
        f.seek(max(0, self.offset - 96))
        self.tail = f.read(min(self.offset, 96))

    def lines(self):
        try:
            with self.path.open("rb") as f:
                stat = os.fstat(f.fileno())
                if (stat.st_dev, stat.st_ino) != self.identity or stat.st_size < self.offset:
                    self.offset = 0
                elif self.offset:
                    f.seek(self.offset - len(self.tail))
                    if f.read(len(self.tail)) != self.tail:
                        self.offset = 0
                f.seek(self.offset)
                chunk = f.read()
                end = chunk.rfind(b"\n") + 1
                self.offset += end
                self._remember(f)
        except OSError:
            return []
        return chunk[:end].decode("utf-8", "replace").splitlines()
