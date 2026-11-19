import pytest

from netlauncher import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NET_LAUNCHER_HOME", str(tmp_path / "Данные лаунчера"))
    return paths.layout()
