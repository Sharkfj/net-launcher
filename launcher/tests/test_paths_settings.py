import sys

import pytest

from netlauncher import paths
from netlauncher.settings import Settings, load_settings, recommended_ram_mb, save_settings


def test_layout_under_env_root(home):
    assert home.root.name == "Данные лаунчера"
    for d in (home.minecraft, home.instances, home.snapshots, home.cache):
        assert d.is_dir()
    assert paths.game_dir(home) == home.instances / "net"


def test_windows_root(monkeypatch):
    monkeypatch.delenv("NET_LAUNCHER_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\Вася\AppData\Roaming")
    assert str(paths.data_root()).endswith("NET Launcher")


def test_linux_root_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("NET_LAUNCHER_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert paths.data_root() == tmp_path / "net-launcher"


def test_settings_roundtrip_and_corrupt(home):
    s = Settings(max_ram_mb=6144, last_world="Новый мир")
    save_settings(home.settings_file, s)
    assert load_settings(home.settings_file) == s
    home.settings_file.write_text("{oops", encoding="utf-8")
    assert load_settings(home.settings_file) == Settings()


def test_settings_ignores_unknown_keys(home):
    home.settings_file.write_text('{"max_ram_mb": 4096, "bogus": 1}', encoding="utf-8")
    assert load_settings(home.settings_file).max_ram_mb == 4096


@pytest.mark.parametrize("total,exp", [(8192, 4096), (16384, 8192), (32768, 8192), (4096, 3072), (12000, 5632)])
def test_recommended_ram(total, exp):
    assert recommended_ram_mb(total) == exp
