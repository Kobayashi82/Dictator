"""Tema claro / oscuro / el del sistema."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dictador.ui import style

THEMES = ("claro", "oscuro", "sistema")
THEME_LABELS = {"claro": "Claro", "oscuro": "Oscuro", "sistema": "Como Windows"}

_current = "claro"
_listening = False


def _system_is_dark() -> bool:
    return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def apply_theme(theme: str) -> None:
    """Cambia los colores de toda la aplicación. Los widgets con un método `theme_changed` lo reciben."""
    global _current, _listening
    app = QApplication.instance()
    if app is None:
        return
    _current = theme
    hints = QApplication.styleHints()
    if theme == "sistema":
        hints.unsetColorScheme()
        dark = _system_is_dark()
        if not _listening:
            # Si Windows cambia de claro a oscuro con el programa abierto, se sigue el cambio.
            hints.colorSchemeChanged.connect(lambda _s: _current == "sistema" and _refresh(_system_is_dark()))
            _listening = True
    else:
        dark = theme == "oscuro"
        # Los diálogos de Windows (abrir, guardar, imprimir) también siguen el tema.
        hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    _refresh(dark)


def _refresh(dark: bool) -> None:
    app = QApplication.instance()
    if style.DARK == dark and app.styleSheet():
        return
    style.set_dark(dark)
    app.setStyleSheet(style.stylesheet())
    for widget in app.allWidgets():
        hook = getattr(widget, "theme_changed", None)
        if callable(hook):
            hook()
        widget.update()
