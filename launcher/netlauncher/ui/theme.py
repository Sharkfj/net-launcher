"""Colours, fonts and the stylesheet of the launcher."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).parent / "assets"

TOKENS = {
    "window": "rgba(12,18,32,0.72)",
    "window_opaque": "#0C1220",
    "card": "rgba(255,255,255,0.06)",
    "card_hover": "rgba(255,255,255,0.09)",
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

DISPLAY = "Unbounded"
BODY = "Onest"


def qcolor(token: str) -> QColor:
    v = TOKENS.get(token, token)
    if v.startswith("rgba("):
        r, g, b, a = (x.strip() for x in v[5:-1].split(","))
        return QColor(int(r), int(g), int(b), round(float(a) * 255))
    return QColor(v)


def font(size: float, weight: int = 400, family: str = BODY) -> QFont:
    f = QFont(family)
    f.setPointSizeF(size)
    f.setVariableAxis(QFont.Tag("wght"), float(weight))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def load_fonts() -> None:
    for name in ("Unbounded.ttf", "Onest.ttf"):
        QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / name))


def qss() -> str:
    t = TOKENS
    return f"""
    QWidget {{ color: {t['text']}; }}
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
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
    QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.10); border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {t['text']}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
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
