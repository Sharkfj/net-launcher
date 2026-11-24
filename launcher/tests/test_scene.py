import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _run(spring, seconds, fps):
    steps = round(seconds * fps)
    for _ in range(steps):
        spring.step(1 / fps)
    return spring.value


def test_spring_same_result_at_10_and_120_fps():
    from netlauncher.ui.scene.springs import Spring
    a, b = Spring(0, k=7), Spring(0, k=7)
    a.target = b.target = 1
    assert abs(_run(a, 1, 10) - _run(b, 1, 120)) < 0.01


def test_spring_settles():
    from netlauncher.ui.scene.springs import Spring
    s = Spring(0, k=7)
    s.target = 1
    _run(s, 4, 60)
    assert abs(s.value - s.target) < 1e-3


def test_springs_group_targets():
    from netlauncher.ui.scene.springs import Springs
    g = Springs({"a": 0.0, "b": 2.0}, k={"a": 20.0})
    g.set_targets({"a": 1.0})
    for _ in range(180):
        g.step(1 / 60)
    assert abs(g["a"] - 1.0) < 1e-3 and g["b"] == 2.0


def test_city_layers_deterministic(qapp):
    from netlauncher.ui.scene.city import CityScene
    a, b = CityScene(seed=1), CityScene(seed=1)
    la, lb = a.static_layers(), b.static_layers()
    assert len(la) == 4
    assert all(x == y for x, y in zip(la, lb))
    assert la[0].width() == CityScene.LW + 2 * CityScene.MARGIN
    assert la[0].height() == CityScene.LH + 2 * CityScene.MARGIN_Y


def test_city_cameras_table():
    from netlauncher.ui.scene.city import CityScene
    assert CityScene.CAMERAS == {"home": (0, 0, 0), "packs": (-1.3, -.3, .05), "official": (1.2, -.9, .07),
                                 "friends": (-.7, .5, .03), "settings": (1.4, .7, .06)}


@pytest.mark.parametrize("w,h", [(980, 620), (1180, 720), (1920, 1080)])
def test_city_edges_covered_at_extremes(qapp, w, h):
    from netlauncher.ui.scene.city import CityScene
    scene = CityScene(seed=1)
    for _ in range(10):
        scene.step(1 / 30)
    for cam in CityScene.CAMERAS.values():
        for px in (-1, 1):
            for py in (-1, 1):
                img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(Qt.GlobalColor.transparent)
                p = QPainter(img)
                scene.render(p, QSize(w, h), QPointF(px, py), cam)
                p.end()
                for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
                    assert img.pixelColor(x, y).alpha() == 255, (w, h, cam, px, py, x, y)


def _pump(ms):
    from PySide6.QtCore import QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QApplication.processEvents()


@pytest.fixture
def view(qapp):
    from PySide6.QtWidgets import QWidget
    from netlauncher.ui import anim
    from netlauncher.ui.scene.view import SceneView
    anim.set_enabled(True)
    host = QWidget()
    host.resize(600, 400)
    v = SceneView(host)
    v.setGeometry(0, 0, 600, 400)
    host.show()
    yield v
    host.close()
    anim.set_enabled(True)


def test_sceneview_timer_60fps(view):
    assert view.timer.interval() == 16


def test_springs_moving():
    from netlauncher.ui.scene.springs import Springs
    g = Springs({"a": 0.0})
    assert not g.moving()
    g.set_targets({"a": 1.0})
    assert g.moving()
    for _ in range(300):
        g.step(1 / 60)
    assert not g.moving()


def test_scene_freezes_after_camera_settles(view):
    view.set_scene("city", animate=False)
    view.set_tab("settings")
    assert view.running()
    _pump(4000)
    assert not view.running()
    view.set_tab("home")
    assert view.running()


def test_sceneview_pauses_when_hidden_or_game(view):
    view.set_scene("city", animate=False)
    assert view.running()
    view.set_paused("game", True)
    assert not view.running() and not view.timer.isActive()
    view.set_paused("game", False)
    assert view.running()
    view.parentWidget().hide()
    assert not view.timer.isActive()


def test_sceneview_static_when_animations_off(view):
    from netlauncher.ui import anim
    anim.set_enabled(False)
    view.set_scene("city")
    assert not view.timer.isActive()
    img = view.snapshot()
    assert not img.isNull() and img.pixelColor(300, 200).alpha() == 255


def test_switch_during_transition_lands_on_last(view):
    view.set_scene("city", animate=False)
    view.set_scene("studio")
    assert view.transition_active()
    view.set_scene("city")
    view.set_scene("studio")
    _pump(1000)
    assert view.kind == "studio" and not view.transition_active()


def test_plain_scene_is_flat(view):
    view.set_scene("plain", animate=False)
    img = view.snapshot()
    colors = {img.pixelColor(x, y).name() for x, y in ((30, 30), (300, 200), (570, 370), (10, 390))}
    assert colors == {"#0a101d"}


def test_dissolve_clears_left_first(qapp):
    from netlauncher.ui.scene.view import dissolve_mask_widths
    early = dissolve_mask_widths(0.2, cols=100)
    late = dissolve_mask_widths(1.0, cols=100)
    assert len(early) == 16 and max(early) < 100 and min(late) >= 100


def test_deep_shade_darkens_whole_width(view):
    view.set_scene("city", animate=False)
    view.set_shade("deep")
    shaded, raw = view.grab().toImage(), view.snapshot()
    dark = (4, 7, 14)
    cover = []
    for x in (view.width() - 40, view.width() // 2):
        for y in range(40, view.height() - 40, 20):
            r, sh = raw.pixelColor(x, y), shaded.pixelColor(x, y)
            for ch_raw, ch_sh, d in ((r.red(), sh.red(), dark[0]), (r.green(), sh.green(), dark[1]), (r.blue(), sh.blue(), dark[2])):
                if ch_raw - d > 12:
                    cover.append((ch_raw - ch_sh) / (ch_raw - d))
    assert cover and sum(cover) / len(cover) >= 0.7
