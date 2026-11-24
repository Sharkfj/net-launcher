"""Reversible performance settings for a local pack."""
from __future__ import annotations

from pathlib import Path

from netlauncher import localpacks
from netlauncher.library import AlreadyInstalled, Library, NotAvailable
from netlauncher.net import HttpError

_COMMON = ("ferrite-core", "modernfix", "entityculling", "immediatelyfast")
MODS = {"fabric": ("sodium", "lithium", *_COMMON), "quilt": ("sodium", "lithium", *_COMMON),
        "neoforge": ("sodium", *_COMMON), "forge": ("embeddium", *_COMMON)}
OPTIONS = {"renderDistance": "10", "simulationDistance": "8", "renderClouds": '"fast"', "entityShadows": "false"}
JVM = ["-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
       "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC", "-XX:G1NewSizePercent=30",
       "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M", "-XX:G1ReservePercent=20"]


def _options(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _write(path, lines):
    tmp = path.with_suffix(".fps.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)


def tune_options(game_dir):
    path = game_dir / "options.txt"
    lines = _options(path)
    saved = dict.fromkeys(OPTIONS)
    seen = set()
    for i, line in enumerate(lines):
        key, _, value = line.partition(":")
        if key in OPTIONS:
            saved[key] = value
            lines[i] = key + ":" + OPTIONS[key]
            seen.add(key)
    lines.extend(k + ":" + v for k, v in OPTIONS.items() if k not in seen)
    _write(path, lines)
    return saved


def enable(library, lp, progress):
    if lp.fps:
        return lp.fps_mods
    folder = library.game_dir / "mods"
    folder.mkdir(exist_ok=True)
    before = {p.name for p in folder.iterdir()}
    owned = set()
    try:
        for slug in MODS.get(lp.loader, ()):
            try:
                project = library.mr.project(slug)
                plan = library.plan_install(project.id, "mod")
                plan.items = [(p, v) for p, v in plan.items if v.primary_file.filename not in before
                              and v.primary_file.filename + ".disabled" not in before]
                for _, version in plan.items:
                    name = version.primary_file.filename
                    if Path(name).name != name or "\\" in name or not name.endswith(".jar"):
                        raise ValueError("Invalid mod filename")
                    owned.add(name)
                library.install(plan, "mod", progress)
            except (AlreadyInstalled, NotAvailable):
                continue
            except HttpError as e:
                if e.status != 404:
                    raise
        lp.fps_options = tune_options(library.game_dir)
    except Exception:
        for name in owned:
            (folder / name).unlink(missing_ok=True)
        raise
    lp.fps_mods = sorted(name for name in owned if (folder / name).is_file())
    lp.fps = True
    return lp.fps_mods


def disable(library, lp):
    path = library.game_dir / "options.txt"
    lines = []
    for line in _options(path):
        key, _, value = line.partition(":")
        if key in lp.fps_options and OPTIONS.get(key) == value:
            previous = lp.fps_options[key]
            if previous is None:
                continue
            line = key + ":" + previous
        lines.append(line)
    if path.exists():
        _write(path, lines)
    for name in lp.fps_mods:
        if Path(name).name == name and "\\" not in name and name.endswith(".jar"):
            for suffix in ("", ".disabled"):
                (library.game_dir / "mods" / (name + suffix)).unlink(missing_ok=True)
    lp.fps, lp.fps_mods, lp.fps_options = False, [], {}


def configure(ctx, lp, enabled, progress):
    lib = Library(localpacks.game_dir(ctx.lay, lp.id), ctx.lay.snapshots / lp.id, ctx.modrinth,
                  ctx.http, ctx.lay.cache, lp.mc_version, lp.loader)
    if enabled:
        enable(lib, lp, progress)
    else:
        disable(lib, lp)
    localpacks.save(ctx.lay, lp)
