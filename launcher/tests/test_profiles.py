import os
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from netlauncher.auth_ely import offline_account
from netlauncher.ui import anim
from netlauncher.ui.app import make_context
from netlauncher.ui.pages import FACTORY
from netlauncher.ui.window import MainWindow
from tests.fakes import FakeHttp


def test_avatar_opens_local_profile(home):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    ctx = make_context(home, FakeHttp(offline=True))
    ctx.settings.first_run_done = True
    ctx.accounts.save(offline_account("Miner"))
    anim.set_enabled(False)
    win = MainWindow(ctx, FACTORY)
    try:
        win.show()
        QTest.mouseClick(win.rail.avatar, Qt.MouseButton.LeftButton)
        app.processEvents()
        page = win.page("profile")
        assert win.current_page() == "profile" and page.nickname.text() == "Miner"
        assert page.kind.text() == "Локальный профиль"
        assert not page.apply.isEnabled() and not page.comments.form.isVisible()
        assert not page.skin_btn.isVisible()
    finally:
        win.close()
        anim.set_enabled(True)


def test_author_cosmetics_offline_and_badge(home):
    import hashlib
    import json
    from netlauncher.auth_ely import Account
    from netlauncher.ui import profile_style, supporter
    app = QApplication.instance() or QApplication([])
    ctx = make_context(home, FakeHttp(offline=True))
    ctx.settings.first_run_done = True
    uuid = profile_style.DEVELOPER_UUID
    ctx.accounts.save(Account("Dev", uuid, "", ""))
    key = "ABCD-EFGH-JKLM-NPQR"
    digest = hashlib.sha256(key.replace("-", "").encode()).hexdigest()
    (home.root / "author-cosmetics.json").write_text(json.dumps({"uuid": uuid, "digest": digest}))
    win = MainWindow(ctx, FACTORY)
    try:
        win.show()
        win.open_profile()
        app.processEvents()
        page = win.page("profile")
        assert page.developer.isVisible() and page.developer.toolTip() == "Разработчик"
        assert page.support.submit.isEnabled()
        page.support.entry.setText("AAAA-AAAA-AAAA-AAAA")
        page.support.submit.click()
        assert not supporter.active(ctx)
        page.support.entry.setText(key.lower())
        QTest.keyClick(page.support.entry, Qt.Key_Return)
        assert supporter.active(ctx) and page.save_appearance.isEnabled()
        assert page.pack.currentData() is None
        style = dict(font="mono", color="mint", motion="shimmer", frame="gold")
        for field, value in style.items():
            box = page.style_boxes[field]
            box.setCurrentIndex(box.findData(value))
        assert page.nickname.style == style and page.avatar.frame_style == "gold"
        page.save_appearance.click()
        assert win.rail.avatar.frame_style == "gold"
        reopened = make_context(home, FakeHttp(offline=True))
        assert supporter.active(reopened) and supporter.saved_style(reopened) == style
        ctx.accounts.save(Account("Dev", "1234", "", ""))
        page.on_shown()
        assert not page.developer.isVisible() and not supporter.active(ctx)
        assert not page.save_appearance.isEnabled() and not page.avatar.supporter
    finally:
        win.close()


def test_guest_profile_skin_independent_of_comments_and_client_version(home, monkeypatch):
    from netlauncher import skin
    from netlauncher.ui import jobs
    from netlauncher.ui.skinview import default_skin
    app = QApplication.instance() or QApplication([])
    ctx = make_context(home, FakeHttp(offline=True))
    ctx.settings.first_run_done = True
    ctx.accounts.save(offline_account("Viewer"))
    win = MainWindow(ctx, FACTORY)
    delivered = []
    monkeypatch.setattr(jobs, "run", lambda fn, **kw: delivered.append(kw.get("on_done")))
    try:
        win.show()
        win.open_profile("PlayerA")
        first = delivered[-1]
        win.open_profile("PlayerB")
        second = delivered[-1]
        page = win.page("profile")
        assert page.skin_column.isVisible() and page.scroll.x() < page.skin_column.x()
        assert not page.comments.form.isVisible()
        second(skin.Skin(default_skin().png, True))
        first(skin.Skin(default_skin().png, False))
        assert page.skin_model.slim and page.avatar.has_face()
        assert not page.skin_status.text()
        win.open_profile("PlayerC")
        delivered[-1](None)
        assert not page.skin_model.slim and page.skin_status.text()
        home_page = win.page("home")
        home_page._skin_loaded(skin.Skin(default_skin().png, True))
        win.open_profile()
        assert page.skin_column.isVisible() and page.skin_model.slim
        assert win.scene.scene() is win.scene.profile_studio
        late_guest = delivered[-1]
        late_guest(None)
        assert page.skin_model.slim
        win.open_page("home")
        assert win.scene.scene() is not win.scene.profile_studio
    finally:
        win.close()
