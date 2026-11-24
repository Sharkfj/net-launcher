import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QElapsedTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget

from netlauncher.ui import anim, theme
from netlauncher.ui.app import AppContext, make_context
from netlauncher.ui.window import PAGES, RAIL, MainWindow
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
    assert [name for name, _ in RAIL] == ["home", "packs", "official", "friends", "settings"]
    assert [name for name, _ in PAGES] == ["home", "packs", "official", "friends", "settings", "pack", "profile"]
    for name in [n for n, _ in PAGES] + ["mods", "resourcepacks", "shaders", "snapshots"]:
        assert isinstance(win.page(name), QWidget)
    for name, title in RAIL:
        assert win.nav_button(name).title == title
    assert win.current_page() == "home"


def test_rail_order_and_hover_tip(win):
    assert [b.name for b in win.rail.ordered()] == [name for name, _ in RAIL]
    b = win.nav_button("friends")
    win.rail.show_tip(b)
    pump(260)
    assert win.rail.tip.isVisible() and win.rail.tip.text() == "Друзья"
    win.rail.hide_tip()
    pump(260)
    assert not win.rail.tip.isVisible()


def test_subpages_highlight_packs(win):
    win.open_page("mods")
    assert win.current_page() == "mods" and win.rail.active == "packs"


def test_open_page_sets_scene_tab(win):
    win.open_page("friends")
    assert win.scene.tab == "friends"
    win.open_page("shaders")
    assert win.scene.tab == "packs"


def test_scene_fills_window(win):
    win.resize(1000, 640)
    pump(30)
    assert win.scene.geometry() == win.rect()


def test_update_chip(win, monkeypatch):
    opened = []
    monkeypatch.setattr("netlauncher.ui.window.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    assert not win.update_chip.isVisible()
    win.show_update("0.3.1", "https://example.net/dl")
    assert win.update_chip.isVisible() and win.update_chip.text() == "Вышла 0.3.1"
    win.update_chip.clicked.emit()
    assert opened == ["https://example.net/dl"]


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
    assert "Oswald" in fams and "Onest" in fams


def test_no_blur_module():
    import importlib.util
    assert importlib.util.find_spec("netlauncher.ui.blur") is None


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
    win.open_page("friends")
    pump(450)
    ind = win.rail.indicator.geometry()
    btn = win.nav_button("friends").geometry()
    assert abs(ind.center().y() - btn.center().y()) <= 1


def test_widget_fonts_survive_stylesheet(win):
    from PySide6.QtWidgets import QLabel
    title = next(l for l in win.page("home").findChildren(QLabel) if l.text() == "Играть")
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


def test_toggle_knob_stretches_mid_travel(qapp):
    from netlauncher.ui.widgets import Toggle
    t = Toggle()
    t._set_knob(0.0)
    rest = t.knob_rect().width()
    t._set_knob(0.5)
    assert t.knob_rect().width() > rest * 1.4
    t._set_knob(1.0)
    assert abs(t.knob_rect().width() - rest) < .5


def test_rail_indicator_flows_between_tabs(win):
    win.open_page("settings")
    pump(500)
    win.open_page("home")
    pump(140)
    assert win.rail.indicator.height() > 30
    pump(600)
    assert win.rail.indicator.height() == 22


def test_bar_liquid_phase_moves(qapp):
    from netlauncher.ui.widgets import SmoothBar
    b = SmoothBar(height=6)
    b.resize(300, 6)
    b.show()
    b.set_fraction(.5)
    start = b.phase
    pump(300)
    assert b.phase != start
    b.hide()
    assert not b.timer.isActive()


def test_accent_button_liquid_follows_cursor(qapp):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from netlauncher.ui.widgets import AccentButton
    btn = AccentButton("Играть", big=True)
    btn.resize(240, 56)
    btn.show()
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(60, 20), QPointF(60, 20), Qt.MouseButton.NoButton,
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(btn, ev)
    assert btn.liquid_pos == QPointF(60, 20)
