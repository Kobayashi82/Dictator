"""Tema claro / oscuro / el del sistema."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

THEMES = ("sistema", "claro", "oscuro")
THEME_LABELS = {"sistema": "Como el sistema", "claro": "Claro", "oscuro": "Oscuro"}


def apply_theme(theme: str) -> None:
    hints = QApplication.styleHints()
    if theme == "claro":
        hints.setColorScheme(Qt.ColorScheme.Light)
    elif theme == "oscuro":
        hints.setColorScheme(Qt.ColorScheme.Dark)
    else:
        hints.unsetColorScheme()
