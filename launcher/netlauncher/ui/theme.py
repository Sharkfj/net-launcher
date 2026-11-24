"""Colours, fonts and the stylesheet of the launcher."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QFileSystemWatcher
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication
from netlauncher import local_design

ASSETS = Path(__file__).parent / "assets"

TOKENS = {
    "window": "rgba(12,18,32,0.72)",
    "window_opaque": "#0C1220",
    "card": "rgba(16,24,40,0.88)",
    "card_hover": "rgba(24,35,58,0.92)",
    "border": "rgba(255,255,255,0.08)",
    "accent": "#4C9AFF",
    "accent_hover": "#6AAEFF",
    "accent_pressed": "#3A86F0",
    "on_accent": "#071224",
    "text": "#E8EEF8",
    "muted": "#9AA8BF",
    "faint": "#5E6B82",
    "danger": "#FF7A7A",
    "ok": "#6FD6A8",
}

DISPLAY = "Oswald"
BODY = "Onest"
_design = local_design.DEFAULTS.copy()
_base_tokens = TOKENS.copy()


def page_inset() -> int:
    return _design["page_inset"]


def qcolor(token: str) -> QColor:
    v = TOKENS.get(token, token)
    if v.startswith("rgba("):
        r, g, b, a = (x.strip() for x in v[5:-1].split(","))
        return QColor(int(r), int(g), int(b), round(float(a) * 255))
    return QColor(v)


def font(size: float, weight: int = 400, family: str = BODY) -> QFont:
    f = QFont(family)
    selected = _design["title_font"] if family == DISPLAY else _design["body_font"] if family == BODY else family
    f.setFamilies([selected, family] if family != selected else [family])
    f.setPointSizeF(size * _design["font_scale"] / 100)
    f.setVariableAxis(QFont.Tag("wght"), float(weight))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def load_fonts() -> None:
    for name in ("Oswald.ttf", "Onest.ttf"):
        QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / name))


def qss() -> str:
    t = TOKENS
    return f"""
    QWidget {{ color: {t['text']}; }}
    QWidget#chatSheet {{ background: #121C30; border: 1px solid {t['border']}; border-radius: 14px; }}
    QFrame#incomingMessage {{ background: #1A263C; border-radius: 10px; }}
    QFrame#outgoingMessage {{ background: #203855; border-radius: 10px; }}
    QFrame#outgoingMessage QToolButton {{ border: none; color: {t['muted']}; padding: 1px 5px; }}
    QFrame#outgoingMessage QToolButton:hover, QFrame#outgoingMessage QToolButton:focus {{ color: {t['text']}; }}
    QToolButton#chatAuthor {{ border: 0; font-weight: 600; color: {t['text']}; padding: 1px; }}
    QToolButton#chatAuthor:hover, QToolButton#chatAuthor:focus {{ color: {t['accent']}; }}
    QToolTip {{ background: #142036; color: {t['text']}; border: 1px solid {t['border']}; padding: 6px 8px;
               border-radius: 8px; }}
    QLineEdit, QPlainTextEdit, QSpinBox {{ background: rgba(255,255,255,0.05); border: 1px solid {t['border']};
               border-radius: 10px; padding: 8px 12px; selection-background-color: {t['accent']};
               selection-color: {t['on_accent']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border: 1px solid {t['accent']}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.14); border-radius: 3px; min-height: 40px; }}
    QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.24); }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px 4px; }}
    QScrollBar::handle:horizontal {{ background: rgba(255,255,255,0.14); border-radius: 3px; min-width: 40px; }}
    QScrollBar::handle:horizontal:hover {{ background: rgba(255,255,255,0.24); }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; width: 0;
               background: none; }}
    QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.10); border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {t['text']}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
    QComboBox {{ background: rgba(255,255,255,0.05); border: 1px solid {t['border']}; border-radius: 10px;
               padding: 7px 12px; }}
    QComboBox:hover {{ border: 1px solid rgba(255,255,255,0.16); }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: #121C30; border: 1px solid {t['border']};
               selection-background-color: rgba(76,154,255,0.22); outline: none; }}
    QComboBox#compactCombo {{ combobox-popup: 0; padding-right: 30px; }}
    QComboBox#compactCombo:focus {{ border-color: {t['accent']}; }}
    QComboBox#compactCombo::down-arrow {{ image: none; width: 0; }}
    QComboBox#compactCombo QListView {{ background: #121C30; padding: 4px; border-radius: 8px; }}
    QComboBox#compactCombo QListView::item {{ min-height: 29px; padding: 1px 8px; border-radius: 5px; }}
    QComboBox#compactCombo QListView::item:selected {{ background: #294361; color: {t['text']}; }}
    QLabel[role="muted"] {{ color: {t['muted']}; }}
    QLabel[role="faint"] {{ color: {t['faint']}; }}
    QLabel[role="danger"] {{ color: {t['danger']}; }}
    QMenu {{ background: #121C30; border: 1px solid {t['border']}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: rgba(76,154,255,0.18); }}
    """


def apply(app: QApplication) -> None:
    load_fonts()
    app.setStyle("Fusion")
    _apply_palette(app)


def _apply_palette(app):
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, qcolor("window_opaque"))
    pal.setColor(QPalette.ColorRole.WindowText, qcolor("text"))
    pal.setColor(QPalette.ColorRole.Base, QColor(18, 26, 44))
    pal.setColor(QPalette.ColorRole.Text, qcolor("text"))
    pal.setColor(QPalette.ColorRole.Button, QColor(24, 34, 56))
    pal.setColor(QPalette.ColorRole.ButtonText, qcolor("text"))
    pal.setColor(QPalette.ColorRole.Highlight, qcolor("accent"))
    pal.setColor(QPalette.ColorRole.HighlightedText, qcolor("on_accent"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, qcolor("faint"))
    app.setPalette(pal)
    app.setFont(font(10.5))
    app.setStyleSheet(qss())


def current_positions():
    return _design["positions"]


def apply_design(app, values):
    global _design
    values = local_design.validate(values)
    if values == _design:
        return
    for widget in app.topLevelWidgets():
        if hasattr(widget, "placements"):
            widget.placements.apply(values["positions"])
    if all(values[k] == _design[k] for k in values if k != "positions"):
        _design = values
        return
    old_scale = _design["font_scale"]
    fonts = []
    weight_axis = QFont.Tag("wght")
    for widget in app.allWidgets():
        current = widget.font()
        families = current.families()
        if (widget.testAttribute(Qt.WidgetAttribute.WA_SetFont) and families and
                families[-1] in (DISPLAY, BODY) and current.pointSizeF() > 0):
            weight = current.variableAxisValue(weight_axis) if current.isVariableAxisSet(weight_axis) else current.weight()
            fonts.append((widget, current.pointSizeF() * 100 / old_scale, weight, families[-1]))
    _design = values
    TOKENS.update(_base_tokens)
    for name in ("accent", "text", "muted"):
        TOKENS[name] = values[name]
    if values["accent"] != local_design.DEFAULTS["accent"]:
        accent = QColor(values["accent"])
        TOKENS.update(accent_hover=accent.lighter(115).name(), accent_pressed=accent.darker(115).name(),
                      on_accent="#071224" if accent.lightnessF() > .48 else "#FFFFFF")
    card = QColor(values["card"])
    if values["card"] != local_design.DEFAULTS["card"]:
        TOKENS["card"] = f"rgba({card.red()},{card.green()},{card.blue()},0.88)"
        hover = card.lighter(125)
        TOKENS["card_hover"] = f"rgba({hover.red()},{hover.green()},{hover.blue()},0.92)"
    _apply_palette(app)
    import shiboken6
    for widget, size, weight, family in fonts:
        if shiboken6.isValid(widget):
            widget.setFont(font(size, weight, family))
    for widget in app.topLevelWidgets():
        if hasattr(widget, "apply_page_inset"):
            widget.apply_page_inset()
        widget.update()


def follow_local_design(app, root):
    directory = root / "interface"
    try:
        directory.mkdir(exist_ok=True)
    except OSError:
        apply_design(app, local_design.read(root))
        return None
    watcher = QFileSystemWatcher([str(directory)], app)
    watcher.directoryChanged.connect(lambda _: apply_design(app, local_design.read(root)))
    apply_design(app, local_design.read(root))
    return watcher
