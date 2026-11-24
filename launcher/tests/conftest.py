import pytest

from netlauncher import i18n, paths


@pytest.fixture(scope="session", autouse=True)
def keep_qt_alive():
    """Keep Qt's shared application alive until test workers and windows are closed."""
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    QThreadPool.globalInstance().waitForDone()
    app.closeAllWindows()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(autouse=True)
def russian_ui():
    """Most tests check the Russian copy; English tests switch explicitly."""
    i18n.set_language("ru")
    yield
    i18n.set_language("ru")


@pytest.fixture(autouse=True)
def safe_desktop(tmp_path, monkeypatch):
    """Shortcuts made during tests land in a temporary folder, never on the real desktop."""
    monkeypatch.setenv("NET_LAUNCHER_DESKTOP", str(tmp_path / "Desktop"))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NET_LAUNCHER_HOME", str(tmp_path / "Данные лаунчера"))
    return paths.layout()
