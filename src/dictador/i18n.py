"""Idioma del programa: textos de la interfaz y del dictado (corrector, órdenes de voz, titubeos).

Los textos se escriben en español y se pasan por `tr()`, que los traduce con el diccionario de `i18n_en`. El idioma
se fija al arrancar, antes de construir la interfaz (algunos textos se leen al importar los módulos); cambiarlo
requiere reiniciar el programa.
"""

from __future__ import annotations

LANGUAGES = ("es", "en")
LANGUAGE_LABELS = {"es": "Español", "en": "English"}

_lang = "es"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGUAGES else system_language()


def language() -> str:
    return _lang


def system_language() -> str:
    try:
        from PySide6.QtCore import QLocale

        return "es" if QLocale.system().language() == QLocale.Language.Spanish else "en"
    except Exception:  # noqa: BLE001
        return "es"


def N_(text: str) -> str:  # noqa: N802 (como en gettext)
    """Marca un texto para traducir más tarde con `tr()` (en constantes que se leen al importar)."""
    return text


def tr(text: str, **values) -> str:
    """El texto en el idioma actual. `values` rellena los {huecos} (en los dos idiomas)."""
    if _lang == "en":
        from dictador.i18n_en import EN

        text = EN.get(text, text)
    return text.format(**values) if values else text
