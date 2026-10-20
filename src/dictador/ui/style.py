"""Estilo visual: colores, fuentes e iconos (aspecto de Windows 11 / Office, claro y con letra grande)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

# -- colores (Fluent claro) -------------------------------------------------------------------------------------------

BACKGROUND = QColor("#F3F3F3")  # fondo de la ventana, como Word
PAGE = QColor("#FFFFFF")
TEXT = QColor("#1B1B1B")
TEXT_SOFT = QColor("#5C5C5C")
BORDER = QColor("#E1E1E1")
HOVER = QColor("#EAEAEA")
PRESSED = QColor("#E0E0E0")
ACCENT = QColor("#0F6CBD")  # azul de Office
ACCENT_HOVER = QColor("#115EA3")
ACCENT_SOFT = QColor("#EBF3FC")
RECORD = QColor("#C42B1C")
RECORD_HOVER = QColor("#A52618")
SUCCESS = QColor("#107C10")
SUCCESS_SOFT = QColor("#DFF6DD")

# -- iconos (Segoe Fluent Icons en Windows 11, Segoe MDL2 Assets en Windows 10: mismos códigos) -----------------------

ICON_MIC = ""
ICON_STOP = ""
ICON_NEW = ""
ICON_OPEN = ""
ICON_SAVE = ""
ICON_WORD = ""
ICON_PRINT = ""
ICON_BIGGER = ""
ICON_SMALLER = ""
ICON_MORE = ""
ICON_CHECK = ""
ICON_ENTER = ""
ICON_PARAGRAPH = ""
ICON_HELP = ""
ICON_IDEA = ""
ICON_WARNING = ""
ICON_DOWNLOAD = ""


def _first_family(*names: str) -> str:
    families = set(QFontDatabase.families())
    return next((n for n in names if n in families), names[-1])


def icon_font(size: float) -> QFont:
    font = QFont(_first_family("Segoe Fluent Icons", "Segoe MDL2 Assets"))
    font.setPointSizeF(size)
    return font


def ui_font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(_first_family("Segoe UI Variable Text", "Segoe UI"))
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


def display_font(size: float, weight: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    font = QFont(_first_family("Segoe UI Variable Display", "Segoe UI"))
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


DOCUMENT_FONT = "Georgia"


def stylesheet() -> str:
    """Hoja de estilo general: menús, avisos, barras de desplazamiento y botones de los diálogos."""
    return f"""
    QWidget {{ color: {TEXT.name()}; }}
    QMainWindow, QDialog {{ background: {BACKGROUND.name()}; }}
    QToolTip {{
        background: #FFFFFF; color: {TEXT.name()}; border: 1px solid {BORDER.name()};
        padding: 6px 10px; border-radius: 6px; font-size: 12pt;
    }}
    QMenu {{
        background: #FFFFFF; border: 1px solid {BORDER.name()}; border-radius: 8px; padding: 6px;
        font-size: 13pt;
    }}
    QMenu::item {{ padding: 9px 28px 9px 16px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {HOVER.name()}; }}
    QMenu::item:disabled {{ color: {TEXT_SOFT.name()}; }}
    QMenu::separator {{ height: 1px; background: {BORDER.name()}; margin: 6px 10px; }}
    QMenu::indicator {{ width: 18px; height: 18px; left: 4px; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{ background: #C8C8C8; border-radius: 4px; min-height: 40px; }}
    QScrollBar::handle:vertical:hover {{ background: #A8A8A8; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; height: 0;
    }}
    QPushButton {{
        background: #FFFFFF; border: 1px solid {BORDER.name()}; border-radius: 8px;
        padding: 10px 26px; font-size: 14pt; min-height: 26px;
    }}
    QPushButton:hover {{ background: #F7F7F7; }}
    QPushButton:pressed {{ background: {PRESSED.name()}; }}
    QPushButton:disabled {{ color: #A0A0A0; }}
    QPushButton[primary="true"] {{
        background: {ACCENT.name()}; color: white; border: 1px solid {ACCENT.name()}; font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER.name()}; }}
    QPushButton[primary="true"]:disabled {{ background: #9CC3E8; border-color: #9CC3E8; color: white; }}
    QPushButton[link="true"] {{
        background: transparent; border: none; color: {ACCENT.name()}; padding: 4px; font-size: 13pt;
    }}
    QPushButton[link="true"]:hover {{ text-decoration: underline; }}
    QComboBox {{
        background: #FFFFFF; border: 1px solid {BORDER.name()}; border-radius: 8px; padding: 8px 12px;
        font-size: 13pt;
    }}
    """
