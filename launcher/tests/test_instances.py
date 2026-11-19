import datetime

import pytest

from netlauncher import instances, localpacks


def test_minecraft_releases(monkeypatch):
    now = datetime.datetime(2026, 1, 1)
    monkeypatch.setattr(instances.mll_utils, "get_version_list", lambda: [
        {"id": "26.3", "type": "release", "releaseTime": now},
        {"id": "26.4-snapshot-1", "type": "snapshot", "releaseTime": now},
        {"id": "1.21.1", "type": "release", "releaseTime": now - datetime.timedelta(days=500)},
        {"id": "b1.7.3", "type": "old_beta", "releaseTime": now}])
    assert instances.minecraft_releases() == ["26.3", "1.21.1"]


def test_loader_versions(monkeypatch):
    class L:
        def is_minecraft_version_supported(self, mc):
            return mc == "1.21.1"

        def get_loader_versions(self, mc, stable_only):
            return ["21.1.267", "21.1.200"]
    monkeypatch.setattr(instances.mll_mod_loader, "get_mod_loader", lambda name: L())
    assert instances.loader_versions("neoforge", "1.21.1") == ["21.1.267", "21.1.200"]
    assert instances.loader_versions("neoforge", "1.8.9") == []
    assert instances.loader_versions("vanilla", "1.21.1") == []


def test_create_unique_ids(home):
    a = instances.create(home, "Мой мир", "1.21.1", "fabric", "0.16.9")
    b = instances.create(home, "Мой мир", "1.21.1", "vanilla", "")
    assert (a.id, b.id) == ("moi-mir", "moi-mir-2")
    assert localpacks.get(home, "moi-mir").loader == "fabric"
    assert (home.instances / "moi-mir" / "mods").is_dir()


def test_loaders_list():
    assert [k for k, _ in instances.LOADERS] == ["vanilla", "fabric", "forge", "neoforge", "quilt"]
