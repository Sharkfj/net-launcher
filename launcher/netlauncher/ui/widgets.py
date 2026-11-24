"""Custom painted widgets: buttons, toggle, progress bar, glass card, avatar."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QGradient, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QAbstractButton, QComboBox, QFrame, QListView, QPushButton, QSizePolicy, QWidget

from netlauncher.ui import anim, icons
from netlauncher.ui.theme import font, qcolor


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))


class _HoverMixin:
    """Animates self._hover between 0 and 1 on enter/leave (120 ms)."""

    _hover = 0.0

    def _animate_hover(self, target: float):
        anim.tween(self._hover, target, 120, self._set_hover)

    def _set_hover(self, v):
        self._hover = float(v)
        self.update()

    def enterEvent(self, e):  # noqa: N802
        self._animate_hover(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self._animate_hover(0.0)
        super().leaveEvent(e)


class CompactCombo(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("compactCombo")
        self.setView(QListView(self))
        self.setMaxVisibleItems(7)
        self.view().setUniformItemSizes(True)
        self.view().setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def showPopup(self):
        view = self.view()
        rows = min(self.count(), self.maxVisibleItems())
        view.ensurePolished()
        height = rows * max(0, view.sizeHintForRow(0)) + 2 * view.frameWidth()
        view.setMinimumHeight(min(height, self.screen().availableGeometry().height() // 2))
        super().showPopup()
        if view.isVisible():
            anim.fade_slide_in(view.viewport(), dx=0, dy=0, ms=130)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(qcolor("muted"), 1.5))
        x, y = self.width() - 17, self.height() / 2
        painter.drawPolyline([QPointF(x-4, y-2), QPointF(x, y+2), QPointF(x+4, y-2)])


class AccentButton(_HoverMixin, QPushButton):
    def __init__(self, text: str = "", icon: str | None = None, big: bool = False, parent=None):
        super().__init__(text, parent)
        self.icon_name, self.big = icon, big
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(15 if big else 10.5, 650))
        self.setMinimumHeight(56 if big else 38)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.liquid_pos = QPointF(-100, -100)

    def mouseMoveEvent(self, e):  # noqa: N802
        self.liquid_pos = e.position()
        self.update()
        super().mouseMoveEvent(e)

    def sizeHint(self):  # noqa: N802
        w = self.fontMetrics().horizontalAdvance(self.text()) + (88 if self.big else 40)
        if self.icon_name:
            w += 28
        return QSize(max(w, 220 if self.big else 0), 56 if self.big else 38)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if not self.isEnabled():
            bg = QColor(76, 154, 255, 70)
        elif self.isDown():
            bg = qcolor("accent_pressed")
        else:
            bg = _mix(qcolor("accent"), qcolor("accent_hover"), self._hover)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        rad = 14 if self.big else 11
        p.drawRoundedRect(r, rad, rad)
        if self.isEnabled() and self._hover > 0:
            # a lighter, cyan-tinted drop under the cursor that mixes into the blue
            shape = QPainterPath()
            shape.addRoundedRect(r, rad, rad)
            blob = QRadialGradient(self.liquid_pos, self.width() * .55)
            blob.setColorAt(0, QColor(150, 225, 255, round(150 * self._hover)))
            blob.setColorAt(.45, QColor(110, 190, 255, round(70 * self._hover)))
            blob.setColorAt(1, QColor(110, 190, 255, 0))
            p.fillPath(shape, blob)
        fg = qcolor("on_accent") if self.isEnabled() else QColor(7, 18, 36, 140)
        p.setPen(fg)
        p.setFont(self.font())
        text_w = self.fontMetrics().horizontalAdvance(self.text())
        icon_w = 0
        if self.icon_name:
            icon_w = 22 if self.big else 16
            total = icon_w + 10 + text_w
            x = (self.width() - total) / 2
            icons.paint(p, self.icon_name, QRectF(x, (self.height() - icon_w) / 2, icon_w, icon_w), fg)
            p.drawText(QRectF(x + icon_w + 10, 0, text_w + 4, self.height()), Qt.AlignmentFlag.AlignVCenter,
                       self.text())
        else:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class GhostButton(_HoverMixin, QPushButton):
    def __init__(self, text: str = "", parent=None, danger: bool = False):
        super().__init__(text, parent)
        self.danger = danger
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(10.5, 520))
        self.setMinimumHeight(38)

    def sizeHint(self):  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 36, 38)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qcolor("border"), 1))
        p.setBrush(QColor(255, 255, 255, round(10 + 14 * self._hover + (10 if self.isDown() else 0))))
        p.drawRoundedRect(r, 11, 11)
        p.setPen(qcolor("danger") if self.danger else (qcolor("text") if self.isEnabled() else qcolor("faint")))
        p.setFont(self.font())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class Toggle(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._knob = 0.0
        self.toggled.connect(lambda on: anim.tween(self._knob, 1.0 if on else 0.0, 160, self._set_knob))

    @property
    def knob(self) -> float:
        return self._knob

    def _set_knob(self, v):
        self._knob = float(v)
        self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = _mix(QColor(255, 255, 255, 36), qcolor("accent"), self._knob)
        if not self.isEnabled():
            track.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 44, 24), 12, 12)
        p.setBrush(QColor("#F4F7FC") if self.isEnabled() else QColor(244, 247, 252, 120))
        p.drawRoundedRect(self.knob_rect(), 9, 9)

    def knob_rect(self) -> QRectF:
        """The knob stretches like a drop halfway through its travel."""
        k = self._knob
        stretch = 12 * 4 * k * (1 - k)
        x = 3 + 20 * k - stretch * k
        return QRectF(x, 3, 18 + stretch, 18)


class SmoothBar(QWidget):
    def __init__(self, parent=None, height: int = 6):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._target = 0.0
        self._shown = 0.0
        self._anim = None
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._flow)

    @property
    def shown(self) -> float:
        return self._shown

    def _flow(self) -> None:
        self.phase = (self.phase + .025) % 1.0
        self.update()

    def _sync_timer(self) -> None:
        if self.isVisible() and 0 < self._target < 1 and anim.enabled():
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._sync_timer()

    def hideEvent(self, e):  # noqa: N802
        self.timer.stop()
        super().hideEvent(e)

    def set_fraction(self, f: float) -> None:
        f = min(max(float(f), 0.0), 1.0)
        self._target = f
        anim.stop(self._anim)
        self._anim = anim.tween(self._shown, f, 350, self._set_shown)
        self._sync_timer()

    def _set_shown(self, v):
        self._shown = float(v)
        self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        rad = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(r, rad, rad)
        if self._shown > 0:
            fill = QRectF(r.x(), r.y(), max(r.height(), r.width() * self._shown), r.height())
            g = QLinearGradient(fill.left(), 0, fill.left() + max(1.0, r.width() * .5), 0)
            g.setSpread(QGradient.Spread.RepeatSpread)
            ph = self.phase
            g.setColorAt(0, qcolor("accent"))
            g.setColorAt((.5 + ph * .5) % 1.0 * .98, QColor(120, 215, 255))
            g.setColorAt(1, qcolor("accent"))
            p.setBrush(g)
            p.drawRoundedRect(fill, rad, rad)
            front = QRadialGradient(QPointF(fill.right() - rad, fill.center().y()), rad * 2.2)
            front.setColorAt(0, QColor(170, 230, 255, 160))
            front.setColorAt(1, QColor(170, 230, 255, 0))
            p.setBrush(front)
            p.drawEllipse(QPointF(fill.right() - rad, fill.center().y()), rad * 1.6, rad * 1.6)


class GlassCard(QFrame):
    def __init__(self, parent=None, radius: int = 16, hoverable: bool = False):
        super().__init__(parent)
        self.radius = radius
        self.hoverable = hoverable
        self.selected = False
        self._hover = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.update()

    def enterEvent(self, e):  # noqa: N802
        if self.hoverable:
            anim.tween(self._hover, 1.0, 120, self._set_hover)
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        if self.hoverable:
            anim.tween(self._hover, 0.0, 160, self._set_hover)
        super().leaveEvent(e)

    def _set_hover(self, v):
        self._hover = float(v)
        self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.selected:
            p.setPen(QPen(qcolor("accent"), 1.4))
            p.setBrush(QColor(76, 154, 255, 22))
        else:
            p.setPen(QPen(_mix(qcolor("border"), QColor(255, 255, 255, 46), self._hover), 1))
            p.setBrush(_mix(qcolor("card"), qcolor("card_hover"), self._hover))
        p.drawRoundedRect(r, self.radius, self.radius)


class Toast(GlassCard):
    """Short message in the bottom-right corner of the window."""

    def __init__(self, parent):
        super().__init__(parent, radius=14)
        from PySide6.QtWidgets import QHBoxLayout, QLabel
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 18, 12)
        lay.setSpacing(10)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.text = QLabel()
        self.text.setFont(font(10.5, 540))
        lay.addWidget(self.dot)
        lay.addWidget(self.text)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade)
        self.hide()

    def show_message(self, text: str, kind: str = "ok") -> None:
        color = qcolor("danger" if kind == "error" else "accent").name()
        self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.text.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move(par.width() - self.width() - 28, par.height() - self.height() - 28)
        self.raise_()
        self.show()
        anim.fade_slide_in(self, dx=0, dy=12, ms=220)
        self.timer.start(3000)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(18, 28, 48, 245))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

    def _fade(self) -> None:
        anim.fade_out(self, ms=180, then=self.hide)


def search_field(placeholder: str = ""):
    """QLineEdit with a magnifier icon on the left."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QLineEdit
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    icons.paint(p, "search", QRectF(0, 0, 32, 32), qcolor("muted"), 2.6)
    p.end()
    field.addAction(QIcon(pm), QLineEdit.ActionPosition.LeadingPosition)
    return field


class Avatar(QWidget):
    """Round-cornered face of the player's skin, or the first letter of the name."""

    clicked = Signal()

    def __init__(self, size: int = 32, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._face: QImage | None = None
        self._letter = "?"
        self.supporter = False
        self.frame_style = "aurora"

    def set_supporter(self, enabled: bool, frame="aurora") -> None:
        self.frame_style = frame
        self.supporter = bool(enabled)
        self.update()

    def set_name(self, name: str) -> None:
        self._letter = (name[:1] or "?").upper()
        self.update()

    def has_face(self) -> bool:
        return self._face is not None and not self._face.isNull()

    def face_image(self):
        return self._face

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_face(self, img: QImage | None) -> None:
        self._face = img
        self.update()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, r.width() * 0.28, r.width() * 0.28)
        p.setClipPath(clip)
        if self._face is not None and not self._face.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            p.drawPixmap(self.rect(), QPixmap.fromImage(self._face))
        else:
            p.fillRect(r, QColor(76, 154, 255, 60))
            p.setPen(qcolor("text"))
            p.setFont(font(self.width() * 0.36, 700))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._letter)
        if self.supporter and self.frame_style != "none":
            border = QLinearGradient(r.topLeft(), r.bottomRight())
            colors = {"gold": ("#FFE4A6", "#CB863A", "#FFEAC6"), "ice": ("#D5F7FF", "#60B8FF", "#D2EEFF")}
            for stop, color in zip((0, .5, 1), colors.get(self.frame_style, ("#73F0DF", "#AC9DFF", "#F8BB84"))):
                border.setColorAt(stop, QColor(color))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(border, 2.5))
            p.drawRoundedRect(r.adjusted(1.25, 1.25, -1.25, -1.25), r.width() * .25, r.width() * .25)
