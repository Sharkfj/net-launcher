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


MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]


def human_date(dt) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]}, {dt:%H:%M}"


def human_size(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} ГБ".replace(".", ",")
    if n >= 1 << 20:
        return f"{round(n / (1 << 20))} МБ"
    return f"{max(1, round(n / 1024))} КБ"


def human_downloads(n: int) -> str:
    if n >= 10_000_000:
        return f"{round(n / 1_000_000)} млн загрузок"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} млн загрузок".replace(".", ",")
    if n >= 1000:
        return f"{round(n / 1000)} тыс. загрузок"
    return f"{n} {plural(n, 'загрузка', 'загрузки', 'загрузок')}"


def confirm(parent, title: str, text: str, ok: str) -> bool:
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton(ok, QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def current_pack(ctx):
    from netlauncher import localpacks
    packs = localpacks.list_installed(ctx.lay)
    if not packs:
        return None
    return next((p for p in packs if p.id == ctx.settings.selected_pack), packs[0])
