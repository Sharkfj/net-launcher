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
