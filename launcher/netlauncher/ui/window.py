"""Frameless glass main window: sidebar, animated page stack, tray."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import (QAbstractButton, QApplication, QHBoxLayout, QLabel, QMenu, QStackedWidget,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from netlauncher.ui import anim, blur, icons
from netlauncher.ui.theme import DISPLAY, font, qcolor
from netlauncher.ui.widgets import Avatar, _HoverMixin, _mix

PAGES = [("home", "Главная"), ("mods", "Моды"), ("resourcepacks", "Ресурспаки"), ("shaders", "Шейдеры"),
         ("snapshots", "Снимки"), ("settings", "Настройки")]
RADIUS = 18
SIDEBAR_W = 208
TITLE_H = 52
EDGE = 6


class NavButton(_HoverMixin, QAbstractButton):
    def __init__(self, name: str, title: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.setText(title)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setFont(font(10.5, 520))
        self._active = 0.0
        self.toggled.connect(lambda on: anim.tween(self._active, 1.0 if on else 0.0, 180, self._set_active))

    def _set_active(self, v):
        self._active = float(v)
        self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover > 0 and self._active < 1:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, round(12 * self._hover * (1 - self._active))))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, 0, 0), 10, 10)
        color = _mix(_mix(qcolor("muted"), qcolor("text"), self._hover * 0.6), qcolor("text"), self._active)
        icons.paint(p, self.name, QRectF(14, (self.height() - 18) / 2, 18, 18),
                    _mix(color, qcolor("accent"), self._active))
        p.setPen(color)
        p.setFont(self.font())
        p.drawText(QRectF(44, 0, self.width() - 48, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())


class Indicator(QWidget):
    """The soft highlight that slides to the active section."""

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(76, 154, 255, 34))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        p.setBrush(qcolor("accent"))
        p.drawRoundedRect(QRectF(0, self.height() * 0.28, 3, self.height() * 0.44), 1.5, 1.5)


class Sidebar(QWidget):
    def __init__(self, on_select: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_W)
        self.on_select = on_select
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 20, 14, 16)
        lay.setSpacing(4)
        brand = QLabel(".NET")
        brand.setFont(font(15, 700, DISPLAY))
        brand.setContentsMargins(12, 0, 0, 0)
        sub = QLabel("Лаунчер")
        sub.setProperty("role", "faint")
        sub.setFont(font(9, 450))
        sub.setContentsMargins(13, 0, 0, 18)
        lay.addWidget(brand)
        lay.addWidget(sub)
        self.indicator = Indicator(self)
        self.indicator.lower()
        self.buttons: dict[str, NavButton] = {}
        for name, title in PAGES:
            b = NavButton(name, title)
            b.clicked.connect(lambda _=False, n=name: self.on_select(n))
            lay.addWidget(b)
            self.buttons[name] = b
        lay.addStretch(1)
        row = QHBoxLayout()
        row.setContentsMargins(10, 0, 4, 0)
        row.setSpacing(10)
        self.avatar = Avatar(30)
        self.account = QLabel("Не вошёл")
        self.account.setFont(font(10, 520))
        row.addWidget(self.avatar)
        row.addWidget(self.account, 1)
        lay.addLayout(row)
        self._active = ""

    def set_active(self, name: str, animate: bool = True) -> None:
        self._active = name
        for n, b in self.buttons.items():
            b.setChecked(n == name)
        target = self.buttons[name].geometry()
        if not target.isValid() or target.isEmpty():
            return
        if animate and self.indicator.isVisible() and self.indicator.geometry().isValid():
            anim.tween(self.indicator.geometry(), target, 260, self.indicator.setGeometry)
        else:
            self.indicator.setGeometry(target)
        self.indicator.show()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if self._active:
            self.indicator.setGeometry(self.buttons[self._active].geometry())

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if self._active:
            self.layout().activate()
            self.indicator.setGeometry(self.buttons[self._active].geometry())


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
        t = QLabel(title)
        t.setFont(font(22, 600, DISPLAY))
        lay.addWidget(t)
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
        self.blurred = False
        self._animating = 0
        self._opened = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = Sidebar(self.open_page)
        root.addWidget(self.sidebar)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 10, 12, 0)
        bar.setSpacing(4)
        bar.addStretch(1)
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
        holder.setContentsMargins(8, 0, 28, 24)
        self.content = holder
        root.addWidget(holder, 1)

        factory = page_factory or {}
        self._pages: dict[str, QWidget] = {}
        for name, title in PAGES:
            w = factory[name](ctx, self) if name in factory else Placeholder(title)
            self._pages[name] = w
            self.stack.addWidget(w)
        self._current = "home"
        self.sidebar.set_active("home", animate=False)
        self._setup_tray()

    # ---------- pages ----------
    def page(self, name: str) -> QWidget:
        return self._pages[name]

    def nav_button(self, name: str) -> NavButton:
        return self.sidebar.buttons[name]

    def current_page(self) -> str:
        return self._current

    def is_animating(self) -> bool:
        return self._animating > 0

    def open_page(self, name: str) -> None:
        self.sidebar.set_active(name)
        if name == self._current and self.stack.currentWidget() is self._pages[name]:
            return
        self._current = name
        w = self._pages[name]
        self.stack.setCurrentWidget(w)
        if hasattr(w, "on_shown"):
            w.on_shown()
        if anim.enabled():
            self._animating += 1
            anim.fade_slide_in(w, dx=24, ms=220, on_done=self._anim_done)

    def _anim_done(self):
        self._animating = max(0, self._animating - 1)

    # ---------- painting / blur ----------
    def _shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        return p

    def _apply_blur(self):
        region = QRegion(self._shape().toFillPolygon().toPolygon())
        self.blurred = blur.enable(self, region)
        self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        shape = self._shape()
        if self.blurred:
            p.fillPath(shape, qcolor("window"))
        else:
            g = QLinearGradient(0, 0, 0, self.height())
            g.setColorAt(0, QColor("#0F1A2E"))
            g.setColorAt(1, QColor("#0A101D"))
            p.fillPath(shape, g)
        sheen = QLinearGradient(0, 0, 0, 220)
        sheen.setColorAt(0, QColor(255, 255, 255, 12))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(shape, sheen)
        side = QPainterPath()
        side.addRect(QRectF(SIDEBAR_W, 0, 1, self.height()))
        p.fillPath(side.intersected(shape), QColor(255, 255, 255, 14))
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.drawPath(shape)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._apply_blur()
        if not self._opened:
            self._opened = True
            if anim.enabled():
                self._animating += 1
                anim.fade_slide_in(self.content, dx=0, dy=14, ms=420, on_done=self._anim_done)
                anim.fade_slide_in(self.sidebar, dx=-10, ms=420)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if self.isVisible():
            self._apply_blur()

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
            if e.position().y() <= TITLE_H or e.position().x() <= SIDEBAR_W:
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

    # ---------- account ----------
    def set_account(self, acc) -> None:
        self.sidebar.account.setText(acc.name if acc else "Не вошёл")
        self.sidebar.avatar.set_name(acc.name if acc else "?")

    # ---------- tray ----------
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip(".NET Launcher")
        menu = QMenu()
        menu.addAction("Показать", self.restore_from_tray)
        menu.addAction("Выход", QApplication.quit)
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
