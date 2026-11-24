import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from netlauncher import skin
from netlauncher.skin import Skin, parts
from tests.fakes import FakeHttp


def test_parts_modern_vs_legacy():
    modern = parts(64, 64, slim=False)
    assert modern["arm_l"].uv == (32, 48) and not modern["arm_l"].mirror
    assert modern["arm_l"].overlay.uv == (48, 48) and modern["head"].overlay.uv == (32, 0)
    assert modern["head"].overlay.inflate == pytest.approx(0.5) and modern["body"].overlay.inflate == pytest.approx(0.25)
    legacy = parts(64, 32, slim=False)
    assert legacy["arm_l"].uv == legacy["arm_r"].uv == (40, 16) and legacy["arm_l"].mirror
    assert legacy["leg_l"].uv == (0, 16) and legacy["leg_l"].mirror
    assert legacy["arm_l"].overlay is None and legacy["body"].overlay is None and legacy["head"].overlay is not None


def test_slim_arm_width():
    assert parts(64, 64, slim=True)["arm_r"].size == (3, 12, 4)
    assert parts(64, 64, slim=False)["arm_r"].size == (4, 12, 4)
    assert parts(64, 64, slim=True)["arm_r"].origin[0] == -7


def test_face_uv_layout():
    head = parts(64, 64, slim=False)["head"]
    f = {name: uv for name, _corners, uv, _n in skin.faces(head)}
    assert f["front"] == (8, 8, 8, 8) and f["top"] == (8, 0, 8, 8) and f["back"] == (24, 8, 8, 8)
    assert f["right"] == (0, 8, 8, 8) and f["left"] == (16, 8, 8, 8)


def _routes(tmp_path, slim=True):
    meta = {"SKIN": {"url": "http://ely.by/storage/skins/x.png", **({"metadata": {"model": "slim"}} if slim else {})}}
    return FakeHttp({skin.TEXTURES.format(name="Shark"): meta}, downloads={"http://ely.by/storage/skins/x.png": b"PNG"})


def test_fetch_slim_and_cache(tmp_path):
    http = _routes(tmp_path)
    s = skin.fetch(http, "Shark", tmp_path)
    assert s == Skin(b"PNG", True)
    n = len(http.calls)
    assert skin.fetch(http, "Shark", tmp_path) == s and len(http.calls) == n


def test_fetch_offline_uses_cache_and_no_skin(tmp_path):
    skin.fetch(_routes(tmp_path, slim=False), "Shark", tmp_path)
    meta = tmp_path / "skins" / "Shark.json"
    data = json.loads(meta.read_text())
    data["fetched"] = time.time() - 7200
    meta.write_text(json.dumps(data))
    assert skin.fetch(FakeHttp(offline=True), "Shark", tmp_path) == Skin(b"PNG", False)
    assert skin.fetch(FakeHttp(offline=True), "Nobody", tmp_path) is None
    assert skin.fetch(FakeHttp({skin.TEXTURES.format(name="Bare"): {}}), "Bare", tmp_path) is None


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _two_tone_png() -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    for x in range(64):
        for y in range(32):
            img.setPixelColor(x, y, QColor(200, 30, 30))   # everything red…
    for x in range(8, 16):
        for y in range(8, 16):
            img.setPixelColor(x, y, QColor(30, 200, 30))   # …except the face, green
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def test_skinview_renders_pixels(qapp):
    from netlauncher.ui.skinview import SkinView3D
    v = SkinView3D(animate=False)
    v.resize(300, 420)
    v.set_skin(Skin(_two_tone_png(), False))
    img = v.grab().toImage()
    c = img.pixelColor(150, 210)
    assert c.alpha() > 0


def test_back_faces_hidden(qapp):
    from netlauncher.ui.skinview import SkinView3D
    v = SkinView3D(animate=False)
    v.resize(300, 420)
    v.set_skin(Skin(_two_tone_png(), False))
    v.set_pose(yaw=0, pitch=0)
    vis = v.visible_faces()
    assert ("head", "front") in vis and ("head", "back") not in vis
    v.set_pose(yaw=180, pitch=0)
    vis = v.visible_faces()
    assert ("head", "back") in vis and ("head", "front") not in vis


def test_default_skin_and_face(qapp):
    from netlauncher.ui.skinview import default_skin, face
    s = default_skin()
    assert not s.slim and len(s.png) > 100
    f = face(s.png)
    assert f.width() == 8 and f.height() == 8 and f.pixelColor(3, 3).alpha() == 255


def test_png_size_and_reject():
    assert skin.png_size(_two_tone_png()) == (64, 64)
    assert skin.check_skin(_two_tone_png()) == (64, 64)
    with pytest.raises(ValueError) as e:
        skin.check_skin(b"not a png")
    assert str(e.value) == "Нужна картинка PNG размером 64×64 или 64×32."
    from PySide6.QtGui import QImage
    from PySide6.QtCore import QBuffer, QIODevice
    img = QImage(128, 128, QImage.Format.Format_ARGB32)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    with pytest.raises(ValueError):
        skin.check_skin(bytes(buf.data()))


def test_fetch_force_bypasses_cache(tmp_path):
    http = _routes(tmp_path)
    skin.fetch(http, "Shark", tmp_path)
    n = len(http.calls)
    skin.fetch(http, "Shark", tmp_path, force=True)
    assert len(http.calls) > n


def _flat_png(rgb=(128, 128, 128)):
    from PySide6.QtCore import QBuffer, QIODevice
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    img.fill(QColor(*rgb))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def _settle(r, seconds=3.0):
    for _ in range(int(seconds * 30)):
        r.step(1 / 30)


def test_renderer_no_wave_or_walk(qapp):
    from netlauncher.ui.skinview import SkinRenderer
    r = SkinRenderer()
    for bad in ("wave", "walk", "greet"):
        with pytest.raises(ValueError):
            r.react(bad)


def test_rim_light_tints_side_faces(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter
    from netlauncher.ui.skinview import SkinRenderer
    r = SkinRenderer(Skin(_flat_png(), False))
    _settle(r)
    rect = QRectF(0, 0, 400, 600)
    img = QImage(400, 600, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    r.paint(p, rect)
    p.end()
    polys = {(f.part, f.name): f.poly for f in r.projected(rect) if f.layer == "base"}
    assert ("head", "front") in polys and ("head", "left") in polys

    def color_at(poly):
        c = poly.boundingRect().center()
        return img.pixelColor(int(c.x()), int(c.y()))
    side, front = color_at(polys[("head", "left")]), color_at(polys[("head", "front")])
    assert side.blue() - side.red() > front.blue() - front.red() + 25


def test_tab_preset_reaches_camera(qapp):
    from netlauncher.ui.skinview import SkinRenderer
    r = SkinRenderer()
    r.set_tab("settings")
    for _ in range(60):
        r.step(0.05)
    want = SkinRenderer.CAMERAS["settings"]
    assert all(abs(a - b) < 0.5 for a, b in zip(r.camera(), want))


def test_camera_and_pose_tables(qapp):
    from netlauncher.ui.skinview import SkinRenderer
    assert SkinRenderer.CAMERAS == {"home": (8.7, -7.9, 94, 4), "packs": (26.6, 0.9, 62.6, 9),
                                    "official": (2.7, -15.9, 87.4, 6), "friends": (-15.6, -4.5, 89.6, 3),
                                    "settings": (19.2, 2.3, 48.7, 11)}
    assert {k: v["ry"] for k, v in SkinRenderer.POSES.items()} == {"home": -.42, "packs": -2.25, "official": -1.35,
                                                                  "friends": -.08, "settings": -.85}


def test_nod_returns_to_idle(qapp):
    from netlauncher.ui.skinview import SkinRenderer
    r = SkinRenderer()
    r.react("nod")
    assert r.reaction == "nod"
    _settle(r, 1.5)
    assert r.reaction == "idle"


def test_turn_head_returns_to_idle(qapp):
    from netlauncher.ui.skinview import SkinRenderer
    r = SkinRenderer()
    r.react("turn_head")
    _settle(r, 2.0)
    assert r.reaction == "idle"


def test_missing_skin_uses_default(qapp):
    from netlauncher.ui.skinview import SkinRenderer, default_skin
    assert SkinRenderer(None).skin_png == default_skin().png


def test_renderer_reuses_cached_image_when_still(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter
    from netlauncher.ui.skinview import SkinRenderer
    r = SkinRenderer()
    _settle(r, 3.0)
    img = QImage(300, 400, QImage.Format.Format_ARGB32_Premultiplied)
    for _ in range(3):
        img.fill(0)
        p = QPainter(img)
        r.paint(p, QRectF(0, 0, 300, 400))
        p.end()
    assert r.renders == 1
    r.set_tab("settings")
    for _ in range(10):
        r.step(0.05)
    p = QPainter(img)
    r.paint(p, QRectF(0, 0, 300, 400))
    p.end()
    assert r.renders == 2


def test_studio_animates_each_moving_frame(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from netlauncher.ui.skinview import SkinRenderer
    renderer = SkinRenderer()
    image = QImage(240, 320, QImage.Format.Format_ARGB32_Premultiplied)
    renderer.set_tab("packs")
    with QPainter(image) as painter:
        for _ in range(20):
            renderer.step(.016)
            renderer.paint(painter, QRectF(0, 0, 240, 320))
    assert renderer.renders >= 18
