"""Small helpers shared by pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from netlauncher.ui.theme import BODY, DISPLAY, font


def label(text: str = "", size: float = 10.5, weight: int = 400, role: str | None = None, display: bool = False,
          wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setFont(font(size, weight, DISPLAY if display else BODY))
    if role:
        lab.setProperty("role", role)
    if wrap:
        lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return lab


def vbox(parent: QWidget | None = None, margins=(0, 0, 0, 0), spacing: int = 8) -> QVBoxLayout:
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay


def hbox(parent: QWidget | None = None, margins=(0, 0, 0, 0), spacing: int = 8) -> QHBoxLayout:
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return lay


def plural(n: int, one: str, few: str, many: str) -> str:
    n100, n10 = n % 100, n % 10
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many
