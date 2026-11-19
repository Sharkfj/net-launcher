"""User settings stored as JSON."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Settings:
    max_ram_mb: int = 0  # 0 = auto (recommended_ram_mb)
    fullscreen: bool = True
    width: int = 1600
    height: int = 900
    animations: bool = True
    author_mode: bool = False
    github_repo: str = ""
    github_token: str = ""
    last_world: str = ""
    source_instance: str = ""
    selected_pack: str = "net"
    curseforge_key: str = ""
    theme: str = "glass"  # "glass" (transparent, blurred) or "solid"
    first_run_done: bool = False


def load_settings(path: Path) -> Settings:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {f.name: f.type for f in fields(Settings)}
    defaults = Settings()
    kwargs = {}
    for name in known:
        if name in raw and isinstance(raw[name], type(getattr(defaults, name))):
            kwargs[name] = raw[name]
    return Settings(**kwargs)


def save_settings(path: Path, s: Settings) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # holds GitHub / CurseForge tokens
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(asdict(s), ensure_ascii=False, indent=2))
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def recommended_ram_mb(total_mb: int) -> int:
    value = min(max(total_mb // 2, 3072), 8192)
    return value - value % 512
