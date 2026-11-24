"""Find published launcher installers and verify their GitHub asset digest."""

import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from netlauncher.catalog import PACK_REPO
from netlauncher.i18n import t
from netlauncher.net import HashMismatch

RELEASES = f"https://api.github.com/repos/{PACK_REPO}/releases"
TAG = re.compile(r"launcher-v(\d+)\.(\d+)\.(\d+)(?:-beta\.?(\d+))?")


@dataclass(frozen=True)
class Update:
    tag: str
    name: str
    url: str
    sha256: str
    size: int


def _version(tag):
    match = TAG.fullmatch(tag)
    if match is None:
        return None
    a, b, c, beta = match.groups()
    return int(a), int(b), int(c), beta is None, int(beta or 0)


def find_update(http, current, *, system=None, machine=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    name = {"win32": "NET-Launcher-Setup.exe", "linux": "NET-Launcher-Linux-Setup.sh"}.get(system)
    if not name or machine not in {"x86_64", "amd64"}:
        raise ValueError(t("Для этой системы нет установщика обновлений."))
    installed = _version("launcher-v" + current)
    candidates = []
    for release in http.get_json(RELEASES, params={"per_page": 30}):
        tag = release.get("tag_name", "")
        version = _version(tag)
        if release.get("draft") or not version or not installed or version <= installed:
            continue
        url = f"https://github.com/{PACK_REPO}/releases/download/{tag}/{name}"
        for asset in release.get("assets", []):
            digest = re.fullmatch(r"sha256:([a-fA-F0-9]{64})", asset.get("digest") or "")
            size = asset.get("size")
            if (asset.get("name") == name and asset.get("state") == "uploaded"
                    and asset.get("browser_download_url") == url and digest and type(size) is int and size > 0):
                candidates.append((version, Update(tag, name, url, digest[1], size)))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def download_update(http, cache: Path, current, progress):
    update = find_update(http, current)
    if update is None:
        return None
    dest = cache / "updates" / update.tag / update.name
    http.download(update.url, dest, sha256=update.sha256, progress=lambda done, _: progress("", done, update.size))
    if dest.stat().st_size != update.size:
        dest.unlink()
        raise HashMismatch(dest)
    return dest
