import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication, QWidget

from netlauncher.ui import anim, blur, theme
from netlauncher.ui.app import AppContext, make_context
from netlauncher.ui.window import PAGES, MainWindow
from tests.fakes import FakeHttp


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


def pump(ms):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QApplication.processEvents()


@pytest.fixture
def win(qapp, home):
    anim.set_enabled(True)
    w = MainWindow(make_context(home, FakeHttp(offline=True)))
    w.show()
    pump(50)
    yield w
    w.close()


def test_window_builds_all_pages(win):
    assert [name for name, _ in PAGES] == ["home", "mods", "resourcepacks", "shaders", "friends", "snapshots",
                                           "settings"]
    for name, title in PAGES:
        assert isinstance(win.page(name), QWidget)
        assert win.nav_button(name).text() == title
    assert win.current_page() == "home"


def test_page_switch_animates_and_lands(win):
    win.open_page("mods")
    assert win.is_animating()
    pump(450)
    assert win.current_page() == "mods" and not win.is_animating()
    assert win.page("mods").graphicsEffect() is None


def test_animations_off_is_instant(win):
    anim.set_enabled(False)
    win.open_page("settings")
    assert win.current_page() == "settings" and not win.is_animating()
    anim.set_enabled(True)


def test_qss_uses_tokens():
    q = theme.qss()
    assert "#4C9AFF" in q and "glow" not in q.lower()
    assert theme.TOKENS["accent"] == "#4C9AFF" and theme.TOKENS["window"] == "rgba(12,18,32,0.72)"


def test_fonts_loaded(qapp):
    from PySide6.QtGui import QFontDatabase
    fams = QFontDatabase.families()
    assert "Unbounded" in fams and "Onest" in fams


def test_blur_noop_offscreen(qapp):
    w = QWidget()
    w.show()
    assert blur.enable(w) is False


def test_jobs_deliver_on_gui_thread(qapp):
    from netlauncher.ui import jobs
    got = {}
    jobs.run(lambda progress: (progress("шаг", 1, 2), 42)[1], on_done=lambda r: got.setdefault("r", r),
             on_progress=lambda *a: got.setdefault("p", a))
    t = QElapsedTimer()
    t.start()
    while "r" not in got and t.elapsed() < 2000:
        QApplication.processEvents()
    assert got == {"p": ("шаг", 1, 2), "r": 42}


def test_jobs_error(qapp):
    from netlauncher.ui import jobs
    got = {}

    def boom(progress):
        raise ValueError("плохо")
    jobs.run(boom, on_done=lambda r: got.setdefault("r", r), on_error=lambda e: got.setdefault("e", e))
    t = QElapsedTimer()
    t.start()
    while "e" not in got and t.elapsed() < 2000:
        QApplication.processEvents()
    assert isinstance(got["e"], ValueError) and "r" not in got


def test_toggle_animates_knob(qapp):
    from netlauncher.ui.widgets import Toggle
    t = Toggle()
    t.show()
    assert not t.isChecked() and t.knob == 0.0
    t.setChecked(True)
    pump(250)
    assert t.knob == pytest.approx(1.0)


def test_smooth_bar_eases_to_value(qapp):
    from netlauncher.ui.widgets import SmoothBar
    b = SmoothBar()
    b.show()
    b.set_fraction(0.5)
    assert b.shown < 0.5
    pump(450)
    assert b.shown == pytest.approx(0.5)
    anim.set_enabled(False)
    b.set_fraction(0.9)
    assert b.shown == pytest.approx(0.9)
    anim.set_enabled(True)


def test_nav_indicator_follows_active(win):
    win.open_page("snapshots")
    pump(450)
    ind = win.sidebar.indicator.geometry()
    btn = win.nav_button("snapshots").geometry()
    assert abs(ind.center().y() - btn.center().y()) <= 1


def test_widget_fonts_survive_stylesheet(win):
    from PySide6.QtWidgets import QLabel
    brand = next(l for l in win.sidebar.findChildren(QLabel) if l.text() == ".NET")
    assert brand.font().family() == "Unbounded" and brand.font().pointSizeF() == pytest.approx(15)
    title = next(l for l in win.page("home").findChildren(QLabel) if l.text() == "Главная")
    assert title.font().pointSizeF() == pytest.approx(22)


def test_stagger_keeps_layout_positions(qapp):
    from PySide6.QtWidgets import QLabel, QVBoxLayout
    anim.set_enabled(True)
    box = QWidget()
    lay = QVBoxLayout(box)
    box.resize(300, 400)
    box.show()
    pump(20)
    rows = []
    for i in range(5):
        lab = QLabel(f"row {i}")
        lab.setFixedHeight(40)
        lay.addWidget(lab)
        rows.append(lab)
    anim.stagger(rows)          # rows were just added: the layout has not placed them yet
    pump(700)
    ys = [r.y() for r in rows]
    assert ys == sorted(ys) and len(set(ys)) == 5
    assert all(r.graphicsEffect() is None for r in rows)


def test_job_result_after_signals_deleted_does_not_raise(qapp):
    from netlauncher.ui import jobs
    job = jobs.Job(lambda progress: 1, ())
    import shiboken6
    shiboken6.delete(job.signals)
    job.run()  # must not raise "Signal source has been deleted"
