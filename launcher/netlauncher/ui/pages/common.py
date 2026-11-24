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


class FpsControl(QWidget):
    def __init__(self):
        super().__init__()
        from netlauncher.i18n import t
        from netlauncher.ui.widgets import Toggle
        self.toggle = Toggle()
        title = t("Режим FPS")
        hint = t("Прорисовка — 10 чанков. Лаунчер настроит Java и добавит совместимые моды для ускорения игры.")
        self.toggle.setAccessibleName(title)
        self.toggle.setAccessibleDescription(hint)
        row = hbox(self, spacing=10)
        row.addWidget(self.toggle)
        text = vbox(spacing=2)
        text.addWidget(label(title, 10.5, 620))
        text.addWidget(label(hint, 9.5, role="muted", wrap=True))
        row.addLayout(text, 1)


def plural(n: int, one: str, few: str, many: str) -> str:
    from netlauncher.i18n import plural as _plural
    return _plural(n, one, few, many)


MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _ru() -> bool:
    from netlauncher.i18n import language
    return language() == "ru"


def _dec(x: float) -> str:
    s = f"{x:.1f}"
    return s.replace(".", ",") if _ru() else s


def human_date(dt) -> str:
    if _ru():
        return f"{dt.day} {MONTHS[dt.month - 1]}, {dt:%H:%M}"
    return f"{MONTHS_EN[dt.month - 1]} {dt.day}, {dt:%H:%M}"


def human_size(n: int) -> str:
    ru = _ru()
    if n >= 1 << 30:
        return f"{_dec(n / (1 << 30))} {'ГБ' if ru else 'GB'}"
    if n >= 1 << 20:
        return f"{round(n / (1 << 20))} {'МБ' if ru else 'MB'}"
    return f"{max(1, round(n / 1024))} {'КБ' if ru else 'KB'}"


def human_downloads(n: int) -> str:
    ru = _ru()
    if n >= 10_000_000:
        return f"{round(n / 1_000_000)} млн загрузок" if ru else f"{round(n / 1_000_000)}M downloads"
    if n >= 1_000_000:
        return f"{_dec(n / 1_000_000)} млн загрузок" if ru else f"{_dec(n / 1_000_000)}M downloads"
    if n >= 1000:
        return f"{round(n / 1000)} тыс. загрузок" if ru else f"{round(n / 1000)}K downloads"
    return f"{n} {plural(n, 'загрузка', 'загрузки', 'загрузок')}"


def confirm(parent, title: str, text: str, ok: str) -> bool:
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    from netlauncher.i18n import t
    yes = box.addButton(ok, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(t("Отмена"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def confirm_with_option(parent, title: str, text: str, ok: str, option: str, default: bool = True) -> tuple[bool, bool]:
    """Yes/cancel dialog with one checkbox. Returns (confirmed, checkbox state)."""
    from PySide6.QtWidgets import QCheckBox, QMessageBox
    from netlauncher.i18n import t
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    check = QCheckBox(option)
    check.setChecked(default)
    box.setCheckBox(check)
    yes = box.addButton(ok, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(t("Отмена"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is yes, check.isChecked()


def current_pack(ctx):
    from netlauncher import localpacks
    packs = localpacks.list_installed(ctx.lay)
    if not packs:
        return None
    return next((p for p in packs if p.id == ctx.settings.selected_pack), packs[0])
