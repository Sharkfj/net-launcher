"""Build small fake mod jars for tests."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path


def jar_bytes(toml: str | None = None, fabric: dict | None = None, logo: bytes | None = None,
              logo_name: str = "l.png", nested: dict[str, bytes] | None = None,
              manifest_version: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if toml is not None:
            z.writestr("META-INF/neoforge.mods.toml", toml)
        if fabric is not None:
            z.writestr("fabric.mod.json", json.dumps(fabric))
        if logo is not None:
            z.writestr(logo_name, logo)
        if manifest_version:
            z.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nImplementation-Version: {manifest_version}\n")
        for name, data in (nested or {}).items():
            z.writestr(f"META-INF/jarjar/{name}", data)
        if toml is None and fabric is None and not nested:
            z.writestr("readme.txt", "nothing")
    return buf.getvalue()


def make_jar(path: Path, **kw) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jar_bytes(**kw))
    return path


def toml_for(mod_id: str, name: str = "", version: str = "1.0", license: str = "MIT", url: str = "",
             logo: str = "") -> str:
    lines = [f'license="{license}"', "[[mods]]", f'modId="{mod_id}"', f'version="{version}"',
             f'displayName="{name or mod_id}"']
    if url:
        lines.append(f'displayURL="{url}"')
    if logo:
        lines.append(f'logoFile="{logo}"')
    return "\n".join(lines) + "\n"
