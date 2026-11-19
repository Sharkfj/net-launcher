"""Custom painted widgets: buttons, toggle, progress bar, glass card, avatar."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QFrame, QPushButton, QSizePolicy, QWidget

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


class AccentButton(_HoverMixin, QPushButton):
    def __init__(self, text: str = "", icon: str | None = None, big: bool = False, parent=None):
        super().__init__(text, parent)
        self.icon_name, self.big = icon, big
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font(15 if big else 10.5, 650))
        self.setMinimumHeight(56 if big else 38)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

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
        p.drawRoundedRect(r, 14 if self.big else 11, 14 if self.big else 11)
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
        p.drawEllipse(QRectF(3 + 20 * self._knob, 3, 18, 18))


class SmoothBar(QWidget):
    def __init__(self, parent=None, height: int = 6):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._target = 0.0
        self._shown = 0.0
        self._anim = None

    @property
    def shown(self) -> float:
        return self._shown

    def set_fraction(self, f: float) -> None:
        f = min(max(float(f), 0.0), 1.0)
        self._target = f
        anim.stop(self._anim)
        self._anim = anim.tween(self._shown, f, 350, self._set_shown)

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
            p.setBrush(qcolor("accent"))
            p.drawRoundedRect(fill, rad, rad)


class GlassCard(QFrame):
    def __init__(self, parent=None, radius: int = 16):
        super().__init__(parent)
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qcolor("border"), 1))
        p.setBrush(qcolor("card"))
        p.drawRoundedRect(r, self.radius, self.radius)


class Avatar(QWidget):
    """Round-cornered face of the player's skin, or the first letter of the name."""

    def __init__(self, size: int = 32, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._face: QImage | None = None
        self._letter = "?"

    def set_name(self, name: str) -> None:
        self._letter = (name[:1] or "?").upper()
        self.update()

    def set_face(self, img: QImage | None) -> None:
        self._face = img
        self.update()

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
