"""Estilo visual: colores, fuentes e iconos (aspecto de Windows 11 / Office, con letra grande).

Los colores son variables del módulo que cambian con el tema (`set_dark`): quien pinta debe leerlos como `style.TEXT`
en el momento de pintar, nunca copiarlos al construir.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen, QPixmap

# -- colores ----------------------------------------------------------------------------------------------------------

_LIGHT = {
    "BACKGROUND": "#F3F3F3",  # fondo de la ventana, como Word
    "PAGE": "#FFFFFF",  # la hoja
    "SURFACE": "#FFFFFF",  # barra de arriba, diálogos, tarjetas, menús
    "TEXT": "#1B1B1B",
    "DOC_TEXT": "#202020",  # texto del documento
    "TEXT_SOFT": "#5C5C5C",
    "TEXT_FAINT": "#8A8A8A",  # lo que se está diciendo, textos de ejemplo
    "BORDER": "#E1E1E1",
    "HOVER": "#EAEAEA",
    "PRESSED": "#E0E0E0",
    "TRACK": "#E9E9E9",  # fondo del selector de modo y de las barras
    "TRACK_HOVER": "#DEDEDE",
    "THUMB": "#FFFFFF",  # la opción elegida del selector
    "ACCENT": "#0F6CBD",  # azul de Office
    "ACCENT_HOVER": "#115EA3",
    "ACCENT_SOFT": "#EBF3FC",
    "ACCENT_DISABLED": "#9CC3E8",
    "RECORD": "#C42B1C",
    "RECORD_HOVER": "#A52618",
    "SUCCESS": "#107C10",
    "SUCCESS_SOFT": "#DFF6DD",
    "WARNING": "#C47A00",
    "DISABLED": "#A0A0A0",
    "SCROLL": "#C8C8C8",
    "SCROLL_HOVER": "#A8A8A8",
    "TOAST": "#202020",
    "TOAST_TEXT": "#FFFFFF",
    "HIGHLIGHT": "#C8EBBE",  # palabras cambiadas por el corrector
    "FLASH": "#DFF6DD",  # destello del párrafo recién corregido
}

_DARK = {
    "BACKGROUND": "#1B1B1B",
    "PAGE": "#262626",
    "SURFACE": "#2B2B2B",
    "TEXT": "#F2F2F2",
    "DOC_TEXT": "#ECECEC",
    "TEXT_SOFT": "#B4B4B4",
    "TEXT_FAINT": "#8C8C8C",
    "BORDER": "#3C3C3C",
    "HOVER": "#373737",
    "PRESSED": "#404040",
    "TRACK": "#353535",
    "TRACK_HOVER": "#3F3F3F",
    "THUMB": "#4A4A4A",
    "ACCENT": "#3A96DD",
    "ACCENT_HOVER": "#4FA6EA",
    "ACCENT_SOFT": "#1F3A52",
    "ACCENT_DISABLED": "#2F5272",
    "RECORD": "#D13438",
    "RECORD_HOVER": "#E04A4E",
    "SUCCESS": "#6CCB5F",
    "SUCCESS_SOFT": "#253D22",
    "WARNING": "#F0A830",
    "DISABLED": "#6E6E6E",
    "SCROLL": "#555555",
    "SCROLL_HOVER": "#707070",
    "TOAST": "#E8E8E8",
    "TOAST_TEXT": "#1B1B1B",
    "HIGHLIGHT": "#2E4D2A",
    "FLASH": "#2A4A2A",
}

BACKGROUND = PAGE = SURFACE = TEXT = DOC_TEXT = TEXT_SOFT = TEXT_FAINT = BORDER = HOVER = PRESSED = QColor()
TRACK = TRACK_HOVER = THUMB = ACCENT = ACCENT_HOVER = ACCENT_SOFT = ACCENT_DISABLED = RECORD = RECORD_HOVER = QColor()
SUCCESS = SUCCESS_SOFT = WARNING = DISABLED = SCROLL = SCROLL_HOVER = TOAST = TOAST_TEXT = HIGHLIGHT = FLASH = QColor()
DARK = False


def set_dark(dark: bool) -> None:
    global DARK
    DARK = dark
    globals().update({k: QColor(v) for k, v in (_DARK if dark else _LIGHT).items()})


set_dark(False)

# -- iconos (Segoe Fluent Icons en Windows 11, Segoe MDL2 Assets en Windows 10: mismos códigos) -----------------------

ICON_MIC = ""
ICON_STOP = ""
ICON_NEW = ""
ICON_OPEN = ""
ICON_SAVE = ""
ICON_SAVE_AS = ""
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
ICON_IMPORT = ""
ICON_EXPORT = ""
ICON_BOOK = ""
ICON_HIGHLIGHT = ""
ICON_REFRESH = ""
ICON_SETTINGS = ""
ICON_QUIT = ""
ICON_RECENT = ""
ICON_FONT = ""
ICON_THEME = ""


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


def soft(color: QColor, alpha: int) -> str:
    """El color con transparencia, para hojas de estilo."""
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha})"


# -- dibujos para la hoja de estilo (flechas de los desplegables, marca de las casillas) ------------------------------


def _glyph(name: str, color: QColor) -> str:
    """Dibuja una flecha o una marca en un PNG temporal y devuelve su ruta (las hojas de estilo solo admiten
    imágenes de archivo)."""
    folder = Path(tempfile.gettempdir()) / "dictador-ui"
    path = folder / f"{name}-{color.name()[1:]}.png"
    if path.exists():
        return path.as_posix()
    folder.mkdir(parents=True, exist_ok=True)
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    path_ = QPainterPath()
    points = {
        "down": [(8, 12), (16, 20), (24, 12)],
        "up": [(8, 20), (16, 12), (24, 20)],
        "check": [(7, 16.5), (13, 22.5), (25, 10)],
    }[name]
    path_.moveTo(QPointF(*points[0]))
    for pt in points[1:]:
        path_.lineTo(QPointF(*pt))
    p.drawPath(path_)
    p.end()
    pm.save(str(path))
    return path.as_posix()


def stylesheet() -> str:
    """Hoja de estilo de toda la aplicación, con los colores del tema actual."""
    c = {k: v.name() for k, v in globals().items() if isinstance(v, QColor)}
    down, up, check = _glyph("down", TEXT_SOFT), _glyph("up", TEXT_SOFT), _glyph("check", QColor("white"))
    return f"""
    QWidget {{ color: {c['TEXT']}; }}
    QMainWindow, QDialog {{ background: {c['BACKGROUND']}; }}
    QDialog[surface="true"] {{ background: {c['SURFACE']}; }}
    QToolTip {{
        background: {c['SURFACE']}; color: {c['TEXT']}; border: 1px solid {c['BORDER']};
        padding: 6px 10px; border-radius: 6px; font-size: 12pt;
    }}

    /* -- la hoja y lo que flota sobre ella -- */
    QTextEdit#page {{
        background: {c['PAGE']}; color: {c['DOC_TEXT']}; border: none;
        selection-background-color: {c['ACCENT']}; selection-color: white;
    }}
    QLabel#status {{ color: {c['TEXT_SOFT']}; background: transparent; }}
    QLabel#toast {{
        background: {soft(TOAST, 235)}; color: {c['TOAST_TEXT']}; border-radius: 22px; padding: 11px 24px;
    }}

    /* -- textos -- */
    QLabel[soft="true"] {{ color: {c['TEXT_SOFT']}; }}
    QLabel[heading="true"] {{ color: {c['TEXT_SOFT']}; font-weight: 600; }}
    QLabel[ok="true"] {{ color: {c['SUCCESS']}; }}
    QLabel[warning="true"] {{ color: {c['WARNING']}; }}
    QLabel[accent="true"] {{ color: {c['ACCENT']}; }}
    QLabel[number="true"], QFrame#card QLabel[number="true"] {{
        background: {c['ACCENT']}; color: white; border-radius: 20px;
    }}
    QLabel#micBox {{
        background: {c['PAGE']}; border: 1px solid {c['BORDER']}; border-radius: 12px; padding: 14px;
        color: {c['TEXT_FAINT']};
    }}
    QLabel#micBox[heard="true"] {{ color: {c['DOC_TEXT']}; }}
    QFrame#card {{ background: {c['SURFACE']}; border: 1px solid {c['BORDER']}; border-radius: 14px; }}
    QFrame#card QLabel {{ border: none; background: transparent; }}
    QFrame#panel {{ background: {c['SURFACE']}; border: 1px solid {c['BORDER']}; border-radius: 14px; }}
    QFrame#separator {{ background: {c['BORDER']}; border: none; max-height: 1px; min-height: 1px; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

    /* -- menús (el del botón derecho en el texto) -- */
    QMenu {{
        background: {c['SURFACE']}; border: 1px solid {c['BORDER']}; border-radius: 8px; padding: 6px;
        font-size: 13pt;
    }}
    QMenu::item {{ padding: 9px 28px 9px 16px; border-radius: 6px; color: {c['TEXT']}; }}
    QMenu::item:selected {{ background: {c['HOVER']}; }}
    QMenu::item:disabled {{ color: {c['TEXT_SOFT']}; }}
    QMenu::separator {{ height: 1px; background: {c['BORDER']}; margin: 6px 10px; }}
    QMenu::indicator {{ width: 18px; height: 18px; left: 4px; }}

    /* -- barras de desplazamiento -- */
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{ background: {c['SCROLL']}; border-radius: 4px; min-height: 40px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['SCROLL_HOVER']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 4px; }}
    QScrollBar::handle:horizontal {{ background: {c['SCROLL']}; border-radius: 4px; min-width: 40px; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; height: 0; width: 0;
    }}

    /* -- botones -- */
    QPushButton {{
        background: {c['SURFACE']}; border: 1px solid {c['BORDER']}; border-radius: 8px;
        padding: 10px 26px; font-size: 14pt; min-height: 26px; color: {c['TEXT']};
    }}
    QPushButton:hover {{ background: {c['HOVER']}; }}
    QPushButton:pressed {{ background: {c['PRESSED']}; }}
    QPushButton:disabled {{ color: {c['DISABLED']}; }}
    QPushButton[primary="true"] {{
        background: {c['ACCENT']}; color: white; border: 1px solid {c['ACCENT']}; font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{ background: {c['ACCENT_HOVER']}; }}
    QPushButton[primary="true"]:disabled {{
        background: {c['ACCENT_DISABLED']}; border-color: {c['ACCENT_DISABLED']}; color: white;
    }}
    QPushButton[link="true"] {{
        background: transparent; border: none; color: {c['ACCENT']}; padding: 4px; font-size: 13pt;
    }}
    QPushButton[link="true"]:hover {{ text-decoration: underline; }}
    QPushButton[small="true"] {{ padding: 6px 16px; font-size: 12pt; min-height: 22px; }}
    QPushButton[stepper="true"] {{ padding: 2px 0; font-size: 20pt; min-height: 34px; }}

    /* -- desplegables: misma letra y aspecto que el resto -- */
    QComboBox {{
        background: {c['SURFACE']}; border: 1px solid {c['BORDER']}; border-radius: 8px;
        padding: 8px 40px 8px 14px; font-size: 14pt; min-height: 28px; color: {c['TEXT']};
    }}
    QComboBox:hover {{ background: {c['HOVER']}; }}
    QComboBox:on {{ border-color: {c['ACCENT']}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right; width: 36px; border: none;
    }}
    QComboBox::down-arrow {{ image: url("{down}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{
        background: {c['SURFACE']}; color: {c['TEXT']}; border: 1px solid {c['BORDER']}; padding: 4px;
        outline: none; font-size: 14pt; selection-background-color: {c['ACCENT_SOFT']}; selection-color: {c['TEXT']};
    }}
    QComboBox QAbstractItemView::item {{ min-height: 40px; padding: 2px 10px; border-radius: 6px; }}
    QComboBox QAbstractItemView::item:hover {{ background: {c['HOVER']}; }}
    QComboBox QAbstractItemView::item:selected {{ background: {c['ACCENT_SOFT']}; }}

    /* -- campos de texto y números -- */
    QLineEdit, QPlainTextEdit, QTextBrowser, QAbstractSpinBox {{
        background: {c['PAGE']}; color: {c['TEXT']}; border: 1px solid {c['BORDER']}; border-radius: 8px;
        padding: 6px 10px; font-size: 13pt; selection-background-color: {c['ACCENT']}; selection-color: white;
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus {{ border-color: {c['ACCENT']}; }}
    QAbstractSpinBox {{ padding-right: 30px; min-height: 26px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
        subcontrol-origin: border; width: 28px; border: none; background: transparent;
    }}
    QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
    QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {c['HOVER']}; }}
    QAbstractSpinBox::up-arrow {{ image: url("{up}"); width: 11px; height: 11px; }}
    QAbstractSpinBox::down-arrow {{ image: url("{down}"); width: 11px; height: 11px; }}

    /* -- casillas -- */
    QCheckBox {{ spacing: 10px; font-size: 13pt; }}
    QCheckBox::indicator {{
        width: 20px; height: 20px; border: 1px solid {c['TEXT_FAINT']}; border-radius: 5px;
        background: {c['PAGE']};
    }}
    QCheckBox::indicator:checked {{ background: {c['ACCENT']}; border-color: {c['ACCENT']}; image: url("{check}"); }}
    QCheckBox::indicator:disabled {{ background: {c['TRACK']}; border-color: {c['BORDER']}; }}

    QProgressBar {{
        background: {c['TRACK']}; border: none; border-radius: 5px; max-height: 10px; color: transparent;
    }}
    QProgressBar::chunk {{ background: {c['ACCENT']}; border-radius: 5px; }}
    """
