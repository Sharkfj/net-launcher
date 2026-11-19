import hashlib
import time
from pathlib import Path

import pytest

from netlauncher import gameinstall, launch
from netlauncher.auth_ely import Account
from netlauncher.gameinstall import AUTHLIB_META, GameInstaller, InstalledGame
from netlauncher.launch import LaunchSpec, LogProgress, Stage, apply_fullscreen, build_command, crash_info
from netlauncher.net import HashMismatch
from tests.fakes import FakeHttp

SAMPLE = Path(__file__).parent / "data" / "latest_sample.log"
ACC = Account("Player", "abc", "tok", "ct")


@pytest.fixture
def echo(monkeypatch):
    seen = {}

    def fake(version, mc_dir, options):
        seen.update(options, version=version, mc_dir=str(mc_dir))
        return [options["executablePath"], *options["jvmArguments"], "net.minecraft.Main",
                "--gameDir", options["gameDirectory"]] + (
            ["--quickPlaySingleplayer", options["quickPlaySingleplayer"]] if options.get("quickPlaySingleplayer") else []) + (
            ["--quickPlayMultiplayer", options["quickPlayMultiplayer"]] if options.get("quickPlayMultiplayer") else [])

    monkeypatch.setattr(launch.mll_command, "get_minecraft_command", fake)
    return seen


def spec(tmp_path, **kw):
    base = dict(game=InstalledGame("neoforge-21.1.267", tmp_path / "java"), mc_dir=tmp_path / "mc",
                game_dir=tmp_path / "game", account=ACC, ram_mb=6144, fullscreen=True, width=1600, height=900,
                authlib=tmp_path / "authlib.jar")
    base.update(kw)
    return LaunchSpec(**base)


def test_command_has_ely_agent_and_ram(tmp_path, echo):
    cmd = build_command(spec(tmp_path))
    assert "-Xmx6144m" in cmd and "-Xms2048m" in cmd and f"-javaagent:{tmp_path / 'authlib.jar'}=ely.by" in cmd
    assert "-Dfile.encoding=UTF-8" in cmd
    assert echo["username"] == "Player" and echo["uuid"] == "abc" and echo["token"] == "tok"
    assert echo["launcherName"] == "NETLauncher" and echo["version"] == "neoforge-21.1.267"
    assert not echo.get("customResolution")


def test_windowed_sets_resolution(tmp_path, echo):
    build_command(spec(tmp_path, fullscreen=False, width=1280, height=720))
    assert echo["customResolution"] and echo["resolutionWidth"] == "1280" and echo["resolutionHeight"] == "720"


def test_small_ram_xms(tmp_path, echo):
    assert "-Xms1024m" in build_command(spec(tmp_path, ram_mb=1024))


def test_command_with_cyrillic_dirs(tmp_path, echo):
    gd = tmp_path / "Рабочий стол" / "игра"
    cmd = build_command(spec(tmp_path, game_dir=gd))
    assert cmd[cmd.index("--gameDir") + 1] == str(gd)


def test_quickplay_world_and_server(tmp_path, echo):
    cmd = build_command(spec(tmp_path, world="Новый мир"))
    assert cmd[cmd.index("--quickPlaySingleplayer") + 1] == "Новый мир"
    cmd = build_command(spec(tmp_path, server="play.example.net:25565"))
    assert cmd[cmd.index("--quickPlayMultiplayer") + 1] == "play.example.net:25565"


def test_apply_fullscreen(tmp_path):
    gd = tmp_path / "g"
    gd.mkdir()
    apply_fullscreen(gd, True)
    assert (gd / "options.txt").read_text() == "fullscreen:true\n"
    (gd / "options.txt").write_text("lang:ru_ru\nfullscreen:true\nguiScale:3\n")
    apply_fullscreen(gd, False)
    assert (gd / "options.txt").read_text() == "lang:ru_ru\nfullscreen:false\nguiScale:3\n"


def test_log_progress_on_sample():
    lp = LogProgress()
    events = [e for e in map(lp.feed, open(SAMPLE, encoding="utf-8")) if e]
    stages = [s for s, _ in events]
    assert stages[0] is Stage.STARTING
    order = [Stage.STARTING, Stage.LOADING, Stage.RESOURCES, Stage.MENU, Stage.WORLD]
    firsts = [stages.index(s) for s in order]
    assert firsts == sorted(firsts)
    fracs = [f for _, f in events]
    assert fracs == sorted(fracs) and fracs[-1] <= 1.0


def test_log_progress_idle_menu_fallback():
    lp = LogProgress()
    lp.feed("[x] [main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args")
    lp.feed("[x] [Render thread/INFO] [net.minecraft.client.sounds.SoundEngine/SOUNDS]: Sound engine started")
    assert lp.idle(1.0) is None
    assert lp.idle(3.5) == (Stage.MENU, pytest.approx(0.97))


def test_crash_info(tmp_path):
    gd = tmp_path / "g"
    (gd / "crash-reports").mkdir(parents=True)
    start = time.time() - 1
    rep = gd / "crash-reports" / "crash-2026-11-19_22.30.00-client.txt"
    rep.write_text("---- Minecraft Crash Report ----\n// Oops.\n\nTime: x\nDescription: Rendering overlay\n\n"
                   "java.lang.NullPointerException: Cannot invoke \"x\" because \"y\" is null\n\tat a.b(c)\n\n"
                   "A detailed walkthrough\n...\n\tSuspected Mods: \n\t\tCreate: Chromeware (chromeware)\n\n", encoding="utf-8")
    info = crash_info(gd, start)
    assert info.description == "Rendering overlay" and info.cause.startswith("java.lang.NullPointerException")
    assert "Chromeware" in info.suspects and info.report == rep
    assert crash_info(gd, time.time() + 10) is None


def test_installer_order_and_fast_path(tmp_path, monkeypatch):
    from netlauncher.paths import layout
    lay = layout(tmp_path / "root")
    calls = []
    java = lay.minecraft / "runtime" / "java-runtime-delta" / "bin" / "java"
    monkeypatch.setattr(gameinstall.mll_install, "install_minecraft_version",
                        lambda v, d, callback=None: calls.append(("vanilla", v)))
    monkeypatch.setattr(gameinstall.mll_runtime, "get_version_runtime_information",
                        lambda v, d: {"name": "java-runtime-delta", "javaMajorVersion": 21})

    def install_jvm(name, d, callback=None):
        calls.append(("jvm", name))
        java.parent.mkdir(parents=True, exist_ok=True)
        java.write_text("")
    monkeypatch.setattr(gameinstall.mll_runtime, "install_jvm_runtime", install_jvm)
    monkeypatch.setattr(gameinstall.mll_runtime, "get_executable_path", lambda name, d: str(java))

    class Loader:
        def install(self, mc, d, *, loader_version=None, callback=None, java=None):
            calls.append(("loader", mc, loader_version, java))
            return f"neoforge-{loader_version}"
    monkeypatch.setattr(gameinstall.mll_mod_loader, "get_mod_loader", lambda name: Loader())
    inst = GameInstaller(lay, FakeHttp())
    g = inst.ensure("1.21.1", "neoforge", "21.1.267", lambda *a: None)
    assert g == InstalledGame("neoforge-21.1.267", java)
    assert calls == [("vanilla", "1.21.1"), ("jvm", "java-runtime-delta"), ("loader", "1.21.1", "21.1.267", str(java))]
    calls.clear()
    assert inst.ensure("1.21.1", "neoforge", "21.1.267", lambda *a: None) == g and calls == []


def test_authlib_sha256_and_cache(tmp_path):
    from netlauncher.paths import layout
    lay = layout(tmp_path / "root")
    jar = b"authlib-injector"
    meta = {"version": "1.2.7", "download_url": "https://dl/authlib.jar",
            "checksums": {"sha256": hashlib.sha256(jar).hexdigest()}}
    http = FakeHttp({AUTHLIB_META: meta}, downloads={"https://dl/authlib.jar": jar})
    p = GameInstaller(lay, http).ensure_authlib()
    assert p.read_bytes() == jar and p.name == "authlib-injector-1.2.7.jar"
    assert GameInstaller(lay, FakeHttp(offline=True)).ensure_authlib() == p
    bad = FakeHttp({AUTHLIB_META: {**meta, "version": "1.2.8"}}, downloads={"https://dl/authlib.jar": b"evil"})
    with pytest.raises(HashMismatch):
        GameInstaller(lay, bad).ensure_authlib()
    assert not (lay.cache / "authlib-injector-1.2.8.jar").exists()
