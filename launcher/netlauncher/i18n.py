"""Interface language. Source strings are Russian; t() returns the English text when the language is "en"."""

from __future__ import annotations

LANGS = [("en", "English"), ("ru", "Русский")]
_lang = "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in dict(LANGS) else "en"


def language() -> str:
    return _lang


def t(text: str, **kw) -> str:
    if _lang != "ru":
        from netlauncher.i18n_en import EN
        text = EN.get(text, text)
    return text.format(**kw) if kw else text


def plural(n: int, one: str, few: str, many: str) -> str:
    """Russian forms in, the right form for the current language out."""
    if _lang != "ru":
        from netlauncher.i18n_en import EN_PLURAL
        sg, pl = EN_PLURAL.get(one, (one, many))
        return sg if n == 1 else pl
    n100, n10 = n % 100, n % 10
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many
