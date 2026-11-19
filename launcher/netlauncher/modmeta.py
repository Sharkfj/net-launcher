"""Read mod metadata straight from jar files (NeoForge / Fabric)."""

from __future__ import annotations

import hashlib
import io
import json
import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

TOML_PATHS = ("META-INF/neoforge.mods.toml", "META-INF/mods.toml")


@dataclass
class JarMeta:
    mod_ids: list[str]
    name: str
    version: str
    license: str = ""
    display_url: str = ""
    logo: bytes | None = None
    nested_ids: list[str] = field(default_factory=list)


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _str(v) -> str:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v) if v is not None else ""


def _regex_toml(text: str) -> dict:
    def grab(key: str) -> list[str]:
        return re.findall(rf'^\s*{key}\s*=\s*["\']([^"\']*)["\']', text, re.M)

    ids = grab("modId")
    mods = [{"modId": i} for i in ids]
    for key in ("version", "displayName", "displayURL", "logoFile"):
        vals = grab(key)
        if mods and vals:
            mods[0][key] = vals[0]
    lic = grab("license")
    return {"license": lic[0] if lic else "", "mods": mods}


def _parse_toml(text: str) -> dict:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return _regex_toml(text)
    return data if data.get("mods") else _regex_toml(text)


def _manifest_version(z: zipfile.ZipFile) -> str:
    try:
        mf = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except KeyError:
        return ""
    m = re.search(r"^Implementation-Version:\s*(\S+)", mf, re.M)
    return m.group(1) if m else ""


def _read_zip(z: zipfile.ZipFile, depth: int) -> JarMeta | None:
    names = set(z.namelist())
    meta: JarMeta | None = None
    toml_name = next((p for p in TOML_PATHS if p in names), None)
    if toml_name:
        data = _parse_toml(z.read(toml_name).decode("utf-8", "replace"))
        mods = [m for m in data.get("mods") or [] if isinstance(m, dict) and m.get("modId")]
        if mods:
            first = mods[0]
            version = _str(first.get("version", ""))
            if "${" in version:
                version = _manifest_version(z) or version
            logo = None
            logo_file = first.get("logoFile") or data.get("logoFile")
            if logo_file and logo_file in names:
                logo = z.read(logo_file)
            meta = JarMeta([m["modId"] for m in mods], _str(first.get("displayName") or first["modId"]),
                           version, _str(data.get("license", "")), _str(first.get("displayURL", "")), logo)
    elif "fabric.mod.json" in names:
        try:
            fj = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"), strict=False)
        except ValueError:
            fj = None
        if isinstance(fj, dict) and fj.get("id"):
            icon = fj.get("icon")
            if isinstance(icon, dict):
                icon = next(iter(icon.values()), None)
            contact = fj.get("contact") if isinstance(fj.get("contact"), dict) else {}
            meta = JarMeta([fj["id"]], _str(fj.get("name") or fj["id"]), _str(fj.get("version", "")),
                           _str(fj.get("license", "")), _str(contact.get("homepage", "")),
                           z.read(icon) if icon and icon in names else None)
    nested: list[str] = []
    if depth == 0:
        for n in sorted(names):
            if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                try:
                    inner = _read_zip(zipfile.ZipFile(io.BytesIO(z.read(n))), depth + 1)
                except zipfile.BadZipFile:
                    continue
                if inner:
                    nested.extend(inner.mod_ids)
    if meta is None:
        if depth == 0 and nested:
            return JarMeta(nested, "", _manifest_version(z))
        return None
    meta.nested_ids = nested
    return meta


def read_jar(path: Path) -> JarMeta | None:
    try:
        with zipfile.ZipFile(path) as z:
            meta = _read_zip(z, 0)
    except (zipfile.BadZipFile, OSError, KeyError):
        return None
    if meta is not None and not meta.name:
        meta.name = Path(path).stem
    return meta

