"""Frameless main window: icon rail, animated page stack over a live scene, tray."""

from __future__ import annotations

from netlauncher.i18n import t

from typing import Callable

from PySide6.QtCore import QProcess, QPoint, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QApplication, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QStackedWidget,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from netlauncher.ui import anim, icons
from netlauncher.ui.scene.view import SceneView
from netlauncher.ui.theme import DISPLAY, font, qcolor
from netlauncher.ui.widgets import Avatar, _HoverMixin, _mix

_alive_windows: list = []

RAIL = [("home", "Играть"), ("packs", "Сборки"), ("official", "Официальные"), ("friends", "Друзья"),
        ("settings", "Настройки")]
SECTIONS = ("mods", "resourcepacks", "shaders", "snapshots")  # open_page("mods") = this section of the current pack
SUBPAGES = {"pack": "packs", **{s: "packs" for s in SECTIONS}}
PAGES = RAIL + [("pack", "Сборка"), ("profile", "Профиль")]
RADIUS = 18
RAIL_W = 68
TITLE_H = 52
EDGE = 6


class NavButton(_HoverMixin, QAbstractButton):
    """Icon-only rail button; its title shows in the rail tip on hover."""

    hovered = Signal(object, bool)

    def __init__(self, name: str, title: str, parent=None):
        super().__init__(parent)
        self.name, self.title = name, title
        self.setAccessibleName(title)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 44)
        self._active = 0.0
        self.badge = ""
        self.toggled.connect(lambda on: anim.tween(self._active, 1.0 if on else 0.0, 180, self._set_active))

    def set_badge(self, text: str) -> None:
        self.badge = text
        self.update()

    def _set_active(self, v):
        self._active = float(v)
        self.update()

    def enterEvent(self, e):  # noqa: N802
        super().enterEvent(e)
        self.hovered.emit(self, True)

    def leaveEvent(self, e):  # noqa: N802
        super().leaveEvent(e)
        self.hovered.emit(self, False)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, round(15 * self._hover)))
            p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        color = _mix(_mix(qcolor("muted"), qcolor("text"), self._hover * 0.7), qcolor("text"), self._active)
        icons.paint(p, "play" if self.name == "home" else self.name, QRectF(12, 12, 20, 20), color, 1.7)
        if self.badge:
            p.setFont(font(7.5, 700))
            w = max(16, p.fontMetrics().horizontalAdvance(self.badge) + 8)
            pill = QRectF(self.width() - w - 2, 3, w, 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor("accent"))
            p.drawRoundedRect(pill, 8, 8)
            p.setPen(qcolor("on_accent"))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, self.badge)


class Indicator(QWidget):
    """The thin accent bar that flows to the active rail button; stretched, its colours mix towards cyan."""

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if self.height() > 24:
            g = QLinearGradient(0, 0, 0, self.height())
            g.setColorAt(0, qcolor("accent"))
            g.setColorAt(.5, QColor(120, 215, 255))
            g.setColorAt(1, qcolor("accent"))
            p.setBrush(g)
        else:
            p.setBrush(qcolor("accent"))
        p.drawRoundedRect(QRectF(0, 0, 3, self.height()), 1.5, 1.5)


class RailTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(font(9.5, 520))
        self.setStyleSheet("background: #151f33; color: #e8eefb; border-radius: 8px; padding: 6px 10px;")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()


class Rail(QWidget):
    def __init__(self, on_select: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.setFixedWidth(RAIL_W)
        self.on_select = on_select
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 18, 12, 14)
        lay.setSpacing(6)
        self.icon_slot = QWidget()
        self.icon_slot.setFixedSize(40, 40)
        lay.addWidget(self.icon_slot, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        self.indicator = Indicator(self)
        self.indicator.setFixedWidth(3)
        self.indicator.resize(3, 22)
        self.indicator.hide()
        self.buttons: dict[str, NavButton] = {}
        for name, title in RAIL:
            b = NavButton(name, t(title))
            b.clicked.connect(lambda _=False, n=name: self.on_select(n))
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
            self.buttons[name] = b
        lay.addStretch(1)
        self.avatar = Avatar(34)
        lay.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignHCenter)
        from netlauncher import __version__
        self.version = QLabel(f"v{__version__}")
        self.version.setProperty("role", "faint")
        self.version.setFont(font(7.5, 450))
        self.version.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        version_row = QHBoxLayout()
        version_row.setSpacing(2)
        version_row.addStretch()
        version_row.addWidget(self.version)
        self.update = QPushButton("↓")
        self.update.setFixedSize(19, 20)
        self.update.setToolTip(t("Обновить лаунчер"))
        self.update.setAccessibleName(self.update.toolTip())
        version_row.addWidget(self.update)
        version_row.addStretch()
        lay.addLayout(version_row)
        self.account_name = ""
        self.active = ""
        self.tip: RailTip | None = None

    def ordered(self) -> list[NavButton]:
        return [self.buttons[name] for name, _ in RAIL]

    def set_active(self, name: str, animate: bool = True) -> None:
        self.active = name
        for n, b in self.buttons.items():
            b.setChecked(n == name)
        btn = (self.avatar if name == "profile" else self.buttons[name]).geometry()
        if not btn.isValid() or btn.isEmpty():
            return
        target = QRectF(0, btn.center().y() - 11, 3, 22).toRect()
        if animate and self.indicator.isVisible() and anim.enabled():
            self._flow_to(target)
        else:
            self.indicator.setGeometry(target)
        self.indicator.show()

    def _flow_to(self, target) -> None:
        """Liquid move: the leading edge runs ahead, the tail catches up, so the bar stretches and settles."""
        from PySide6.QtCore import QEasingCurve, QRect
        cur = self.indicator.geometry()
        self._edges = [float(cur.top()), float(cur.bottom() + 1)]
        down = target.top() > cur.top()
        lead, tail = (1, 0) if down else (0, 1)
        ends = [float(target.top()), float(target.bottom() + 1)]

        def setter(i):
            def f(v):
                self._edges[i] = float(v)
                top, bot = min(self._edges), max(self._edges)
                self.indicator.setGeometry(QRect(0, round(top), 3, max(22, round(bot - top))))
            return f
        anim.tween(self._edges[lead], ends[lead], 230, setter(lead), easing=QEasingCurve.Type.OutCubic)
        anim.tween(self._edges[tail], ends[tail], 460, setter(tail), easing=QEasingCurve.Type.InOutCubic)

    def show_tip(self, button: NavButton) -> None:
        if self.tip is None:
            return
        self.tip.setText(button.title)
        self.tip.adjustSize()
        pos = button.mapTo(self.tip.parentWidget(), QPoint(button.width() + 10, (button.height() - self.tip.height()) // 2))
        self.tip.move(pos.x() - 6, pos.y())
        self.tip.show()
        self.tip.raise_()
        anim.tween(float(pos.x() - 6), float(pos.x()), 200, lambda v: self.tip.move(int(v), pos.y()))

    def hide_tip(self) -> None:
        if self.tip is not None:
            self.tip.hide()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if self.active:
            self.set_active(self.active, animate=False)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if self.active:
            self.layout().activate()
            self.set_active(self.active, animate=False)


class WindowButton(_HoverMixin, QAbstractButton):
    def __init__(self, icon: str, danger: bool = False, parent=None):
        super().__init__(parent)
        self.icon_name, self.danger = icon, danger
        self.setFixedSize(34, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover > 0:
            base = QColor(255, 110, 110) if self.danger else QColor(255, 255, 255)
            base.setAlpha(round((70 if self.danger else 22) * self._hover))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(base)
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        icons.paint(p, self.icon_name, QRectF(9, 7, 16, 16), _mix(qcolor("muted"), qcolor("text"), self._hover), 1.5)


class Placeholder(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 8)
        title_label = QLabel(title)
        title_label.setFont(font(22, 600, DISPLAY))
        lay.addWidget(title_label)
        lay.addStretch(1)


class MainWindow(QWidget):
    def __init__(self, ctx, page_factory: dict[str, Callable] | None = None):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(".NET Launcher")
        self.setWindowIcon(icons.app_icon())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.resize(1180, 720)
        self.setMinimumSize(980, 620)
        self.game_status = ("launcher", "", "")
        self._animating = 0
        self._opened = False

        self.scene = SceneView(self, radius=RADIUS)
        self.scene.setGeometry(self.rect())
        from netlauncher.ui.skinview import SkinRenderer
        self.skin = SkinRenderer()
        self.scene.studio.skin = self.skin
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.rail = Rail(self.open_page)
        root.addWidget(self.rail)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 14, 14, 0)
        bar.setSpacing(8)
        bar.addStretch(1)
        self.offline = False
        self.offline_badge = QLabel(t('Нет интернета'))
        self.offline_badge.hide()
        bar.addWidget(self.offline_badge)
        self.rail.update.clicked.connect(self.download_launcher_update)
        self.faces = QHBoxLayout()
        self.faces.setSpacing(6)
        bar.addLayout(self.faces)
        bar.addSpacing(8)
        self.btn_min = WindowButton("minimize")
        self.btn_close = WindowButton("close", danger=True)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_close.clicked.connect(self.close)
        bar.addWidget(self.btn_min)
        bar.addWidget(self.btn_close)
        right.addLayout(bar)
        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.stack, 1)
        holder = QWidget()
        holder.setLayout(right)
        self.content = holder
        self.apply_page_inset()
        root.addWidget(holder, 1)
        self.rail.tip = RailTip(self)
        self.set_rail_icon()
        self.rail.avatar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rail.avatar.setAccessibleName(t("Профиль"))
        self.rail.avatar.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.rail.avatar.clicked.connect(self.open_profile)
        for b in self.rail.buttons.values():
            b.hovered.connect(lambda btn, on: self.rail.show_tip(btn) if on else self.rail.hide_tip())

        factory = page_factory or {}
        self._factory = factory
        ctx.current_window = self
        self._pages: dict[str, QWidget] = {}
        for name, title in PAGES:
            w = factory[name](ctx, self) if name in factory else Placeholder(t(title))
            self._pages[name] = w
            self.stack.addWidget(w)
        self._current = "home"
        self.rail.set_active("home", animate=False)
        self.scene.set_tab("home")
        self.scene.lower()
        from netlauncher.ui.widgets import Toast
        self.toast_widget = Toast(self)
        from netlauncher.ui import theme
        from netlauncher.ui.placement import Placements
        self.placements = Placements(self)
        self.placements.apply(theme.current_positions())
        self._setup_tray()

    # ---------- pages ----------
    def page(self, name: str) -> QWidget:
        if name in SECTIONS:
            pack = self._pages["pack"]
            return pack.sections[name] if hasattr(pack, "sections") else pack
        return self._pages[name]

    def nav_button(self, name: str) -> NavButton:
        return self.rail.buttons[name]

    def current_page(self) -> str:
        return self._current

    def apply_page_inset(self):
        from netlauncher.ui.theme import page_inset
        self.content.setContentsMargins(page_inset(), 0, 0, 24)

    def is_animating(self) -> bool:
        return self._animating > 0

    def open_pack(self, pack_id: str, section: str | None = None) -> None:
        home = self._pages.get("home")
        if pack_id != self.ctx.settings.selected_pack:
            if hasattr(home, "pick_pack"):
                home.pick_pack(pack_id)
            else:
                self.ctx.settings.selected_pack = pack_id
                self.ctx.save()
        pack = self._pages["pack"]
        if hasattr(pack, "show_pack"):
            pack.show_pack(pack_id, section)
        self._show("pack", "pack", shown=False)

    def open_mod_browser(self, pack_id: str) -> None:
        from netlauncher import localpacks

        pack = localpacks.get(self.ctx.lay, pack_id)
        if not localpacks.can_add_mods(pack, self.ctx.settings, getattr(self.ctx, "catalog", None)):
            return
        self.open_pack(pack_id, "mods")
        page = self._pages["pack"]
        if hasattr(page, "sections"):
            page.sections["mods"].open_browser()

    def open_page(self, name: str) -> None:
        if name in SECTIONS:
            pack = self._pages["pack"]
            if hasattr(pack, "show_pack"):
                from netlauncher.ui.pages.common import current_pack
                lp = current_pack(self.ctx)
                pack.show_pack(lp.id if lp else None, name)
            self._show(name, "pack", shown=False)
            return
        self._show(name, name)

    def _show(self, name: str, key: str, shown: bool = True) -> None:
        tab = SUBPAGES.get(name, name)
        self.rail.set_active(tab)
        self.scene.set_tab(tab)
        self.scene.set_shade("home" if name == "home" else "deep")
        if name == self._current and self.stack.currentWidget() is self._pages[key]:
            return
        self._current = name
        w = self._pages[key]
        self.stack.setCurrentWidget(w)
        if shown and hasattr(w, "on_shown"):
            w.on_shown()
        if anim.enabled():
            self._animating += 1
            anim.fade_slide_in(w, dx=0, dy=10, ms=320, on_done=self._anim_done)

    def _anim_done(self):
        self._animating = max(0, self._animating - 1)

    def set_rail_icon(self) -> None:
        from PySide6.QtGui import QPixmap
        from netlauncher.ui.splash import ICON_DIR
        lab = QLabel(self.rail.icon_slot)
        lab.setObjectName("rail_icon")
        lab.setScaledContents(True)
        lab.setGeometry(0, 0, self.rail.icon_slot.width(), self.rail.icon_slot.height())
        lab.setPixmap(QPixmap(str(ICON_DIR / "icon.png")))
        lab.show()

    def open_profile(self, name=None) -> None:
        page = self.page("profile")
        page.target = name
        if self.current_page() == "profile" and hasattr(page, "on_shown"):
            page.on_shown()
        else:
            self.open_page("profile")

    # ---------- scene ----------
    def skin_react(self, name: str) -> None:
        if self.scene.kind == "studio" or name in ("idle",):
            self.skin.react(name)

    def set_game_running(self, on: bool) -> None:
        self.scene.set_paused("game", on)

    # ---------- friends online, top right ----------
    def set_online_faces(self, people: list) -> None:
        """people: [(name, QImage | None)], at most three are shown."""
        while self.faces.count():
            item = self.faces.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for name, img in people[:3]:
            a = Avatar(28)
            a.set_name(name)
            if img is not None:
                a.set_face(img)
            a.setToolTip(name)
            self.faces.addWidget(a)

    # ---------- update chip ----------
    def set_offline(self, on: bool) -> None:
        self.offline = on
        self.offline_badge.setVisible(on)

    def download_launcher_update(self):
        import sys
        from netlauncher import __version__, updater
        from netlauncher.ui import jobs

        button = self.rail.update
        if not button.isEnabled():
            return
        button.setEnabled(False)
        button.setText("…")
        button.setToolTip(t("Проверяю релизы GitHub…"))

        def reset():
            button.setEnabled(True)
            button.setText("↓")
            button.setToolTip(t("Обновить лаунчер"))

        def finished(path):
            reset()
            if path is None:
                self.toast(t("Новых релизов для этой системы нет."))
                return
            answer = QMessageBox.question(
                self, t("Обновить лаунчер"), t("Обновление скачано. Запустить установщик?"))
            if answer != QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
                return
            if sys.platform == "win32":
                ok, _ = QProcess.startDetached(str(path), [])
                if ok:
                    self.toast(t("Установщик запущен."))
                else:
                    self.toast(t("Не удалось запустить установщик."), "error")
            else:
                process = QProcess(self)
                button.setEnabled(False)

                def installed(code, status):
                    reset()
                    if code == 0 and status == QProcess.ExitStatus.NormalExit:
                        self.toast(t("Обновление установлено. Перезапусти лаунчер."))
                    else:
                        self.toast(t("Установка обновления завершилась ошибкой."), "error")
                    process.deleteLater()

                def could_not_start(error):
                    if error == QProcess.ProcessError.FailedToStart:
                        reset()
                        self.toast(t("Не удалось запустить установщик."), "error")
                        process.deleteLater()

                process.finished.connect(installed)
                process.errorOccurred.connect(could_not_start)
                process.start("sh", [str(path)])

        def failed(error):
            reset()
            self.toast(t("Не удалось скачать обновление: {error}", error=str(error)), "error")

        def progress(_, done, total):
            button.setToolTip(t("Скачиваю обновление: {percent} %", percent=min(100, 100 * done // max(total, 1))))

        jobs.run(updater.download_update, self.ctx.http, self.ctx.lay.cache, __version__,
                 on_done=finished, on_error=failed, on_progress=progress)

    # ---------- painting ----------
    def _shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        return p

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        shape = self._shape()
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor("#0F1A2E"))
        g.setColorAt(1, QColor("#0A101D"))
        p.fillPath(shape, g)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if not self._opened:
            self._opened = True
            if anim.enabled():
                self._animating += 1
                anim.fade_slide_in(self.content, dx=0, dy=14, ms=420, on_done=self._anim_done)
                anim.fade_slide_in(self.rail, dx=-10, ms=420)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self.scene.setGeometry(self.rect())

    def changeEvent(self, e):  # noqa: N802
        super().changeEvent(e)
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.Type.WindowStateChange:
            self.scene.set_paused("hidden", bool(self.windowState() & Qt.WindowState.WindowMinimized))

    # ---------- moving / resizing a frameless window ----------
    def _edges(self, pos: QPoint) -> Qt.Edge:
        edges = Qt.Edge(0)
        if pos.x() <= EDGE:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= self.width() - EDGE:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= EDGE:
            edges |= Qt.Edge.TopEdge
        if pos.y() >= self.height() - EDGE:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            edges = self._edges(e.position().toPoint())
            if edges != Qt.Edge(0):
                self.windowHandle().startSystemResize(edges)
                return
            if e.position().y() <= TITLE_H or e.position().x() <= RAIL_W:
                self.windowHandle().startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):  # noqa: N802
        edges = self._edges(e.position().toPoint())
        shapes = {Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor, Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
                  Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor, Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor}
        if edges in shapes:
            self.setCursor(shapes[edges])
        elif edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges != Qt.Edge(0):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(e)

    def toast(self, text: str, kind: str = "ok") -> None:
        self.toast_widget.show_message(text, kind)

    # ---------- language ----------
    def rebuild(self) -> "MainWindow":
        """Recreate the window (after a language change) in the same place, on the same page."""
        page, geo = self._current, self.geometry()
        new = MainWindow(self.ctx, page_factory=self._factory)
        new._opened = True
        new.setGeometry(geo)
        new.show()
        new.open_page(page)
        self.hide()
        self.deleteLater()
        _alive_windows.append(new)
        return new

    # ---------- account ----------
    def set_account(self, acc) -> None:
        self.rail.account_name = acc.name if acc else ""
        from netlauncher.ui.supporter import active, saved_style
        self.rail.avatar.set_supporter(bool(acc and active(self.ctx)), saved_style(self.ctx)["frame"])
        self.rail.avatar.set_name(acc.name if acc else "?")
        self.rail.avatar.setToolTip(t("Профиль"))
        if acc is None:
            self.rail.avatar.set_face(None)

    def set_face(self, img) -> None:
        self.rail.avatar.set_face(img)
        page = self._pages.get("profile")
        if page and hasattr(page, "show_own_face"):
            page.show_own_face(img)

    # ---------- tray ----------
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icons.tray_icon(), self)
        self.tray.setToolTip(".NET Launcher")
        menu = QMenu()
        menu.addAction(t('Показать'), self.restore_from_tray)
        menu.addAction(t('Выход'), QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore_from_tray()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def hide_to_tray(self) -> None:
        if self.tray is not None:
            self.hide()
        else:
            self.showMinimized()

    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
