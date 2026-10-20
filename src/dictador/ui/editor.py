"""Editor: un bloque de QTextDocument por párrafo del modelo, con marcas de estado y resaltado de cambios."""

from __future__ import annotations

import difflib
import re
from contextlib import contextmanager
from itertools import count

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QPainter,
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QMenu, QTextEdit, QToolTip

from dictador.doc.model import DocumentModel, Paragraph
from dictador.ui import style

LINE_SEP = " "  # salto de línea dentro de un bloque (versos)
MARGIN = 26  # margen mínimo; el de la hoja lo fija set_page_margins
PARTIAL_STATE = -2  # bloque que solo contiene el texto en vivo (no pertenece al modelo)

STATUS_TEXT = {
    "dictating": "Dictando…",
    "closed": "Sin corregir",
    "pending": "En cola para corregir",
    "correcting": "Corrigiendo…",
    "corrected": "Corregido",
    "rejected": "Corrección descartada",
    "edited": "Editado a mano",
}

_TOKENS = re.compile(r"\s+|[^\s]+")
LINE_HEIGHT = 135  # interlineado, en %: el texto respira y se lee mejor


def _block_format() -> QTextBlockFormat:
    fmt = QTextBlockFormat()
    fmt.setBottomMargin(12)
    fmt.setLineHeight(LINE_HEIGHT, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    return fmt


def diff_ranges(old: str, new: str) -> list[tuple[int, int]]:
    """Rangos de `new` (inicio, fin) que difieren de `old`, palabra a palabra."""
    a = _TOKENS.findall(old)
    b = _TOKENS.findall(new)
    offsets = [0]
    for tok in b:
        offsets.append(offsets[-1] + len(tok))
    ranges = []
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            start, end = offsets[j1], offsets[j2]
            # Sin resaltar el espacio de los extremos.
            while start < end and new[start].isspace():
                start += 1
            while end > start and new[end - 1].isspace():
                end -= 1
            if start < end:
                ranges.append((start, end))
    return ranges


class DictationEditor(QTextEdit):
    show_diff = Signal(str)
    revert = Signal(str)
    recorrect = Signal(str)

    def __init__(self, model: DocumentModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.highlight_changes = True
        self.italic = False  # el texto en cursiva, como el que aparece mientras se habla
        self._keys: dict[int, str] = {}  # userState del bloque → id del párrafo
        self._key_of: dict[str, int] = {}
        self._next_key = count(1)
        self._sync = False  # cambios hechos por el programa, no por el usuario
        self._depth = 0
        self._dirty = False
        self._partial = ""  # lo que se está diciendo ahora, aún sin cerrar
        self._partial_cursor: QTextCursor | None = None  # selección que cubre ese texto en el documento
        self.show_marks = True  # marcas de estado en el margen (la vista sencilla las oculta)
        self._margins = (MARGIN, MARGIN, MARGIN, MARGIN)  # izquierda, arriba, derecha, abajo
        self._flash_pid = ""
        self._flash = QVariantAnimation(self, duration=1800, startValue=1.0, endValue=0.0,
                                        easingCurve=QEasingCurve.Type.InQuad)
        self._flash.valueChanged.connect(self._paint_flash)

        self.setAcceptRichText(False)
        self.setTabChangesFocus(False)
        self.document().setDocumentMargin(MARGIN)
        self.setMouseTracking(True)
        self.setPlaceholderText("Pulse «Empezar a hablar» y diga lo que quiera escribir.\n"
                                "También puede escribir aquí con el teclado.")

        self.document().contentsChange.connect(self._on_contents_change)
        model.reset.connect(self.rebuild)
        model.paragraph_added.connect(self._on_added)
        model.paragraph_changed.connect(self._on_changed)
        model.paragraph_removed.connect(self._on_removed)

    # -- aspecto --------------------------------------------------------------------------------------------------

    def set_text_font(self, family: str, size: int) -> None:
        font = QFont(family, size)
        self.document().setDefaultFont(font)
        self.rebuild()

    def set_page_margins(self, left: int, top: int, right: int, bottom: int) -> None:
        """Márgenes de la hoja. El de abajo deja sitio al botón flotante para que no tape la última línea."""
        self._margins = (left, top, right, bottom)
        self._apply_margins()

    def _apply_margins(self) -> None:
        root = self.document().rootFrame()
        fmt = root.frameFormat()
        left, top, right, bottom = self._margins
        fmt.setLeftMargin(left)
        fmt.setTopMargin(top)
        fmt.setRightMargin(right)
        fmt.setBottomMargin(bottom)
        root.setFrameFormat(fmt)

    def flash(self, pid: str) -> None:
        """Un destello verde suave sobre el párrafo que acaba de corregirse, que se desvanece solo."""
        if self._block_of(pid) is None:
            return
        self._flash_pid = pid
        self._flash.stop()
        self._flash.start()

    def _paint_flash(self, value) -> None:
        block = self._block_of(self._flash_pid)
        if block is None or float(value) <= 0.01:
            self.setExtraSelections([])
            return
        sel = QTextEdit.ExtraSelection()
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + max(0, block.length() - 1), QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cursor
        color = QColor(style.FLASH)
        color.setAlphaF(float(value))
        sel.format.setBackground(color)
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        self.setExtraSelections([sel])

    def _colors(self) -> dict[str, QColor]:
        return {
            "text": style.DOC_TEXT,
            "dim": style.TEXT_FAINT,
            "highlight": style.HIGHLIGHT,
            "dictating": QColor(90, 140, 220, 140),
            "pending": QColor(150, 150, 150, 150),
            "correcting": QColor(60, 130, 240),
            "corrected": QColor(80, 170, 90),
            "rejected": QColor(225, 140, 40),
            "edited": QColor(150, 110, 200, 170),
        }

    # -- búsqueda de bloques --------------------------------------------------------------------------------------

    def _block_of(self, pid: str) -> QTextBlock | None:
        key = self._key_of.get(pid)
        if key is None:
            return None
        block = self.document().firstBlock()
        while block.isValid():
            if block.userState() == key:
                return block
            block = block.next()
        return None

    def paragraph_at(self, pos: QPoint) -> str | None:
        block = self.cursorForPosition(pos).block()
        return self._keys.get(block.userState())

    def _assign(self, block: QTextBlock, pid: str) -> None:
        key = next(self._next_key)
        old = self._key_of.pop(pid, None)
        if old is not None:
            self._keys.pop(old, None)
        self._keys[key] = pid
        self._key_of[pid] = key
        block.setUserState(key)

    # -- texto en vivo ---------------------------------------------------------------------------------------------

    @contextmanager
    def _programmatic(self):
        """Cambios del programa: no cuentan como ediciones del usuario y el texto en vivo se aparta mientras tanto."""
        self._depth += 1
        outer = self._depth == 1
        if outer:
            self._sync = True
            self._take_partial()
        try:
            yield
        finally:
            if outer:
                self._put_partial()
                self._sync = False
            self._depth -= 1

    def set_partial(self, text: str) -> None:
        """Muestra (o borra, con "") lo que se está diciendo, en cursiva al final del párrafo en dictado."""
        text = " ".join(text.split())
        if text == self._partial:
            return
        self._flush()
        at_bottom = self._at_bottom()
        with self._programmatic():
            self._partial = text
        if at_bottom:
            self._scroll_to_bottom()

    def _take_partial(self) -> None:
        cursor, self._partial_cursor = self._partial_cursor, None
        if cursor is None or not cursor.hasSelection():
            return
        # Al borrar un salto de bloque, Qt se queda con el estado del segundo bloque: se restaura el del primero.
        state = self.document().findBlock(cursor.selectionStart()).userState()
        cursor.removeSelectedText()
        cursor.block().setUserState(-1 if state == PARTIAL_STATE else state)

    def _put_partial(self) -> None:
        if not self._partial:
            return
        doc = self.document()
        cursor = QTextCursor(doc)
        fmt = QTextCharFormat()
        fmt.setForeground(self._colors()["dim"])
        fmt.setFontItalic(True)
        fmt.setFontPointSize(doc.defaultFont().pointSizeF())
        current = self.model.current()
        block = self._block_of(current.id) if current is not None else None
        if block is not None:
            start = block.position() + block.length() - 1
            cursor.setPosition(start)
            joiner = "" if not block.text() else (LINE_SEP if current.mode == "poesia" else " ")
            cursor.insertText(joiner + self._partial, fmt)
        elif not self.model.paragraphs and doc.blockCount() == 1 and not doc.firstBlock().text():
            start = 0
            doc.firstBlock().setUserState(PARTIAL_STATE)
            cursor.insertText(self._partial, fmt)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            start = cursor.position()
            cursor.insertBlock(_block_format(), fmt)
            cursor.block().setUserState(PARTIAL_STATE)
            cursor.insertText(self._partial, fmt)
        self._partial_cursor = QTextCursor(doc)
        self._partial_cursor.setPosition(start)
        self._partial_cursor.setPosition(cursor.position(), QTextCursor.MoveMode.KeepAnchor)

    # -- del modelo al editor -------------------------------------------------------------------------------------

    def rebuild(self) -> None:
        with self._programmatic():
            self._keys.clear()
            self._key_of.clear()
            doc = self.document()
            doc.clear()
            self._apply_margins()
            cursor = QTextCursor(doc)
            for i, p in enumerate(self.model.paragraphs):
                if i > 0:
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    cursor.insertBlock()
                self._assign(cursor.block(), p.id)
                self._render(cursor.block(), p)
            doc.clearUndoRedoStacks()
        self.viewport().update()

    def _on_added(self, index: int, pid: str) -> None:
        self._flush()
        p = self.model.get(pid)
        if p is None:
            return
        at_bottom = self._at_bottom()
        with self._programmatic():
            doc = self.document()
            cursor = QTextCursor(doc)
            if len(self.model.paragraphs) == 1 and doc.blockCount() == 1 and not doc.firstBlock().text():
                block = doc.firstBlock()  # documento vacío: se usa su único bloque
            elif index == 0:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                cursor.insertBlock()
                block = doc.firstBlock()
                block.setUserState(-1)
            else:
                prev = self._block_of(self.model.paragraphs[index - 1].id)
                if prev is None:
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                else:
                    cursor.setPosition(prev.position() + prev.length() - 1)
                cursor.insertBlock()
                block = cursor.block()
            self._assign(block, pid)
            self._render(block, p)
        if at_bottom:
            self._scroll_to_bottom()

    def _on_changed(self, pid: str) -> None:
        self._flush()
        p = self.model.get(pid)
        block = self._block_of(pid)
        if p is None or block is None:
            return
        at_bottom = self._at_bottom()
        with self._programmatic():
            self._render(block, p)
        self.viewport().update()
        if at_bottom:
            self._scroll_to_bottom()

    def _on_removed(self, pid: str) -> None:
        self._flush()
        block = self._block_of(pid)
        key = self._key_of.pop(pid, None)
        if key is not None:
            self._keys.pop(key, None)
        if block is None:
            return
        with self._programmatic():
            cursor = QTextCursor(block)
            if self.document().blockCount() == 1:
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                self.document().firstBlock().setUserState(-1)
            elif block.next().isValid():
                cursor.movePosition(QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
            else:
                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cursor.setPosition(block.position() + block.length() - 1, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
        self.viewport().update()

    def _render(self, block: QTextBlock, p: Paragraph) -> None:
        """Pone el texto y los formatos del párrafo en su bloque sin mover el cursor del usuario si no hace falta."""
        text = p.text.replace("\n", LINE_SEP)
        current = block.text()
        start = block.position()
        cursor = QTextCursor(block)
        if current != text:
            if text.startswith(current):
                # Lo normal al dictar: solo se añade texto al final.
                cursor.setPosition(start + len(current))
                cursor.insertText(text[len(current) :])
            else:
                cursor.setPosition(start)
                cursor.setPosition(start + len(current), QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(text)

        colors = self._colors()
        bfmt = _block_format()
        bfmt.setHeadingLevel(1 if p.style == "title" else 0)
        bfmt.setTopMargin(10 if p.style == "title" else 0)
        cursor.setPosition(start)
        cursor.setBlockFormat(bfmt)

        base = QTextCharFormat()
        base.setForeground(colors["dim"] if p.status == "dictating" else colors["text"])
        base.setBackground(Qt.BrushStyle.NoBrush)
        base.setFontWeight(QFont.Weight.Bold if p.style == "title" else QFont.Weight.Normal)
        default_size = self.document().defaultFont().pointSizeF()
        base.setFontPointSize(default_size * 1.5 if p.style == "title" else default_size)
        base.setFontItalic(self.italic and p.style != "title")
        cursor.setPosition(start)
        # setBlockCharFormat deja el bloque sin maquetar (el texto desaparecía hasta el siguiente cambio): va antes de
        # setCharFormat, que sí lo vuelve a maquetar.
        cursor.setBlockCharFormat(base)
        cursor.setPosition(start + len(text), QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(base)
        if not text:
            self.document().markContentsDirty(start, 1)

        if self.highlight_changes and p.status == "corrected" and not p.show_raw and p.corrected is not None:
            hl = QTextCharFormat()
            hl.setBackground(colors["highlight"])
            for a, b in diff_ranges(p.raw, p.corrected):
                cursor.setPosition(start + a)
                cursor.setPosition(start + b, QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(hl)

    def refresh_formats(self) -> None:
        with self._programmatic():
            for p in self.model.paragraphs:
                block = self._block_of(p.id)
                if block is not None:
                    self._render(block, p)
        self.viewport().update()

    def theme_changed(self) -> None:
        """Cambio de tema: los colores de los párrafos salen de `style`."""
        self.refresh_formats()

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

    # -- del editor al modelo (ediciones del usuario) -------------------------------------------------------------

    def _on_contents_change(self, _pos: int, removed: int, added: int) -> None:
        if self._sync or (removed == 0 and added == 0):
            return
        if not self._dirty:
            self._dirty = True
            QTimer.singleShot(0, self._flush)

    def _flush(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        self.reconcile()

    def reconcile(self) -> None:
        """Pasa al modelo lo que el usuario ha cambiado: textos, párrafos nuevos, borrados y uniones."""
        self._dirty = False
        with self._programmatic():  # el texto en vivo no es del usuario: fuera mientras se compara
            self._reconcile()
        self.viewport().update()

    def _reconcile(self) -> None:
        model = self.model
        order: list[str] = []
        seen: set[str] = set()
        block = self.document().firstBlock()
        changed_structure = False
        while block.isValid():
            text = block.text().replace(LINE_SEP, "\n")
            pid = self._keys.get(block.userState())
            if pid is None or pid in seen or model.get(pid) is None:
                is_lone_empty = self.document().blockCount() == 1 and not text
                if is_lone_empty:
                    block.setUserState(-1)
                    block = block.next()
                    continue
                p = model.user_insert(len(order), text)
                self._assign(block, p.id)
                pid = p.id
                changed_structure = True
            else:
                model.user_edit(pid, text)
            seen.add(pid)
            order.append(pid)
            block = block.next()

        if changed_structure or order != [p.id for p in model.paragraphs]:
            for pid in [p.id for p in model.paragraphs if p.id not in seen]:
                key = self._key_of.pop(pid, None)
                self._keys.pop(key, None)
            model.user_reorder(order)

    # -- marcas de estado en el margen ----------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.show_marks:
            return
        colors = self._colors()
        painter = QPainter(self.viewport())
        layout = self.document().documentLayout()
        offset = -self.verticalScrollBar().value()
        block = self.document().firstBlock()
        height = self.viewport().height()
        while block.isValid():
            pid = self._keys.get(block.userState())
            p = self.model.get(pid) if pid else None
            if p is not None and p.status in colors and p.style != "title":
                rect = layout.blockBoundingRect(block).translated(0, offset)
                if rect.bottom() >= 0 and rect.top() <= height:
                    color = colors[p.status]
                    if p.status == "corrected" and p.show_raw:
                        color = colors["pending"]
                    x = self._margins[0] - 14
                    painter.fillRect(QRectF(x, rect.top() + 3, 3, max(4.0, rect.height() - 6)), color)
                elif rect.top() > height:
                    break
            block = block.next()
        painter.end()

    def _in_margin(self, pos: QPoint) -> bool:
        return self.show_marks and pos.x() < self._margins[0] - 4

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._in_margin(pos):
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if self.paragraph_at(pos) else Qt.CursorShape.ArrowCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and self._in_margin(pos):
            pid = self.paragraph_at(pos)
            if pid:
                menu = QMenu(self)
                self._add_paragraph_actions(menu, pid)
                menu.exec(self.viewport().mapToGlobal(pos))
                return
        super().mousePressEvent(event)

    def viewportEvent(self, event) -> bool:
        if event.type() == event.Type.ToolTip:
            pos = event.pos()
            pid = self.paragraph_at(pos) if self._in_margin(pos) else None
            p = self.model.get(pid) if pid else None
            if p is not None:
                tip = STATUS_TEXT.get(p.status, p.status)
                if p.status == "corrected" and p.show_raw:
                    tip = "Corregido (mostrando el original)"
                if p.reason:
                    tip += f"\n{p.reason}"
                QToolTip.showText(event.globalPos(), tip, self.viewport())
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = self.createStandardContextMenu(event.pos())
        pid = self.paragraph_at(event.pos())
        if pid:
            menu.addSeparator()
            self._add_paragraph_actions(menu, pid)
        menu.exec(event.globalPos())

    def _add_paragraph_actions(self, menu: QMenu, pid: str) -> None:
        p = self.model.get(pid)
        if p is None:
            return
        title = QAction(STATUS_TEXT.get(p.status, p.status), menu)
        title.setEnabled(False)
        menu.addAction(title)
        diff = menu.addAction("Ver cambios…")
        diff.setEnabled(p.corrected is not None and p.status in ("corrected", "edited") and p.corrected != p.raw)
        diff.triggered.connect(lambda: self.show_diff.emit(pid))
        rev = menu.addAction("Mostrar la corrección" if p.show_raw else "Revertir al original")
        rev.setEnabled(p.status == "corrected")
        rev.triggered.connect(lambda: self.revert.emit(pid))
        again = menu.addAction("Volver a corregir")
        again.setEnabled(p.status not in ("dictating", "pending", "correcting") and p.style != "title")
        again.triggered.connect(lambda: self.recorrect.emit(pid))
