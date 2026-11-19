"""Small animation helpers. Everything becomes instant when animations are turned off."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation,
                            QTimer, QVariantAnimation)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

_enabled = True
_running: set[QAbstractAnimation] = set()


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)
    if not _enabled:
        for a in list(_running):
            a.setCurrentTime(a.totalDuration())


def enabled() -> bool:
    return _enabled


def is_running() -> bool:
    return bool(_running)


def stop(a: QAbstractAnimation | None) -> None:
    """Stop an animation that may already have deleted itself."""
    import shiboken6
    if a is not None and shiboken6.isValid(a):
        a.stop()


def _track(a: QAbstractAnimation) -> QAbstractAnimation:
    _running.add(a)
    a.finished.connect(lambda: _running.discard(a))
    return a


def tween(start, end, ms: int, on_value: Callable, on_done: Callable | None = None,
          easing=QEasingCurve.Type.OutCubic) -> QVariantAnimation | None:
    """Animate any interpolatable value (float, QColor, QRect…) and call on_value with each step."""
    if not _enabled or ms <= 0:
        on_value(end)
        if on_done:
            on_done()
        return None
    a = QVariantAnimation()
    a.setStartValue(start)
    a.setEndValue(end)
    a.setDuration(ms)
    a.setEasingCurve(easing)
    a.valueChanged.connect(on_value)
    if on_done:
        a.finished.connect(on_done)
    _track(a).start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return a


def fade_slide_in(w: QWidget, dx: int = 24, dy: int = 0, ms: int = 220, delay: int = 0,
                  on_done: Callable | None = None) -> None:
    if not _enabled:
        if on_done:
            on_done()
        return
    eff = QGraphicsOpacityEffect(w)
    eff.setOpacity(0.0)
    w.setGraphicsEffect(eff)
    end = w.pos()
    start = end + QPoint(dx, dy)
    w.move(start)
    group = QParallelAnimationGroup()
    fade = QPropertyAnimation(eff, b"opacity")
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    move = QPropertyAnimation(w, b"pos")
    move.setStartValue(start)
    move.setEndValue(end)
    for a in (fade, move):
        a.setDuration(ms)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(a)

    def finished():
        # never drop the effect inside its own animation's finished(): defer
        QTimer.singleShot(0, lambda: (w.setGraphicsEffect(None) if w.graphicsEffect() is eff else None))
        if on_done:
            on_done()

    group.finished.connect(finished)
    _track(group)
    if delay > 0:
        QTimer.singleShot(delay, lambda: group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped))
    else:
        group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def fade_out(w: QWidget, ms: int = 160, then: Callable | None = None) -> None:
    if not _enabled:
        if then:
            then()
        return
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    a = QPropertyAnimation(eff, b"opacity")
    a.setStartValue(1.0)
    a.setEndValue(0.0)
    a.setDuration(ms)
    a.setEasingCurve(QEasingCurve.Type.InCubic)

    def finished():
        QTimer.singleShot(0, lambda: w.setGraphicsEffect(None))
        if then:
            then()

    a.finished.connect(finished)
    _track(a).start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def stagger(widgets: list[QWidget], step_ms: int = 30, max_rows: int = 12) -> None:
    for i, w in enumerate(widgets[:max_rows]):
        fade_slide_in(w, dx=0, dy=8, ms=200, delay=i * step_ms)
