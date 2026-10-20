"""Ventana principal: una hoja blanca, un botón grande para hablar y lo mínimo alrededor."""

from __future__ import annotations

import html
import json
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QRect, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence, QLinearGradient, QPainter, QTextDocument
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from dictador import commands
from dictador.config import Settings, localdata_dir, recovery_dir
from dictador.doc import storage
from dictador.doc.model import DocumentModel
from dictador.engine import DictationEngine
from dictador.llm.queue import CorrectionJob, CorrectionQueue
from dictador.ui import style
from dictador.ui.dialogs import DiffDialog, GlossaryDialog
from dictador.ui.editor import DictationEditor
from dictador.ui.theme import apply_theme
from dictador.ui.widgets import IconButton, MenuPanel, MicButton, PillButton, SegmentedControl, Toast, ask, tell

FILE_FILTER = "Documento de Dictador (*.dictador *.dictado)"
FONT_SIZES = (14, 16, 18, 20, 22, 24, 28, 32)
MODE_OPTIONS = [
    ("prosa", "Texto", "Texto normal: se corrigen solas las faltas y la puntuación."),
    ("poesia", "Poesía", "Cada pausa corta es un verso y cada pausa larga, una estrofa."),
    ("notas", "Lista", "Las enumeraciones («primero…, segundo…») se convierten en una lista."),
    ("ninguno", "Sin corregir", "Escribe exactamente lo que dice, sin corregir nada."),
]
PAGE_WIDTH = 900


def documents_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or Path.home())


class _BottomFade(QWidget):
    """Degradado blanco al pie de la hoja, para que el texto pase con suavidad por detrás del botón."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        clear = QColor(style.PAGE)
        clear.setAlpha(0)
        g.setColorAt(0.0, clear)
        g.setColorAt(0.55, style.PAGE)
        g.setColorAt(1.0, style.PAGE)
        p.fillRect(self.rect(), g)
        p.end()


class _Canvas(QWidget):
    """Fondo gris con la hoja blanca en el centro y, flotando sobre ella, el botón de hablar y los avisos."""

    def __init__(self, editor: DictationEditor, parent: QWidget):
        super().__init__(parent)
        self.editor = editor
        editor.setParent(self)
        editor.setFrameShape(DictationEditor.Shape.NoFrame)
        editor.setObjectName("page")
        editor.set_page_margins(72, 56, 72, 190)
        editor.setPlaceholderText("")  # la línea de estado de abajo ya explica qué hacer
        self.fade = _BottomFade(self)

        self.status = QLabel(self)
        self.status.setObjectName("status")
        self.status.setFont(style.ui_font(14))
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._status_fx = QGraphicsOpacityEffect(self.status)
        self.status.setGraphicsEffect(self._status_fx)
        self._status_anim = QPropertyAnimation(self._status_fx, b"opacity", self, duration=160)
        self._next_status = ""
        self._status_anim.finished.connect(self._status_swap)

        self.mic = MicButton(self)
        self.paragraph = PillButton(style.ICON_ENTER, "Nuevo párrafo", self)
        self.paragraph.setToolTip("Termina el párrafo y empieza otro (también puede decir «punto y aparte»)  (Ctrl+Intro)")
        self.toast = Toast(self)

    def page_rect(self) -> QRect:
        w = min(PAGE_WIDTH, self.width() - 40)
        return QRect((self.width() - w) // 2, 22, w, self.height() - 22)

    def resizeEvent(self, event) -> None:
        page = self.page_rect()
        self.editor.setGeometry(page)
        self.fade.setGeometry(page.left(), page.bottom() - 150, page.width() - 14, 151)
        mic = self.mic.sizeHint()
        mx = (self.width() - mic.width()) // 2
        my = self.height() - mic.height() - 20
        self.mic.setGeometry(mx, my, mic.width(), mic.height())
        self.status.setGeometry(page.left(), my - 34, page.width(), 30)
        ph = self.paragraph.sizeHint()
        self.paragraph.setGeometry(mx + mic.width() - 6, my + (mic.height() - ph.height()) // 2, ph.width(), ph.height())
        self.toast.reposition()
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), style.BACKGROUND)
        page = self.page_rect()
        # Sombra suave de la hoja.
        for i, alpha in enumerate((10, 8, 6, 4, 2)):
            shadow = QColor(0, 0, 0, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shadow)
            g = i + 1
            p.drawRoundedRect(page.adjusted(-g, -g + 2, g, g + 2), 6 + g, 6 + g)
        p.setBrush(style.PAGE)
        p.drawRoundedRect(page, 6, 6)
        p.end()

    # -- texto de estado con transición -----------------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        if text == self._next_status:
            return
        self._next_status = text
        self._status_anim.stop()
        self._status_anim.setStartValue(self._status_fx.opacity())
        self._status_anim.setEndValue(0.0)
        self._status_anim.start()

    def _status_swap(self) -> None:
        if self._status_anim.endValue() == 0.0:
            self.status.setText(self._next_status)
            self._status_anim.setStartValue(0.0)
            self._status_anim.setEndValue(1.0)
            self._status_anim.start()


class _Header(QWidget):
    """Barra de arriba con los botones de archivo, el modo y el tamaño de letra."""

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), style.SURFACE)
        p.fillRect(0, self.height() - 1, self.width(), 1, style.BORDER)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, fake_asr: bool = False, fake_llm: bool = False):
        super().__init__()
        self.settings = settings
        self.fake_asr = fake_asr
        self.fake_llm = fake_llm
        self.path: Path | None = None
        self.server = None  # llama-server propio (corrector integrado)
        self.suppress_dictation = False  # el asistente prueba el micrófono sin escribir en el documento
        self._llm_state = ("sin-configurar", "")

        self.model = DocumentModel(self)
        self.model.mode = settings.mode
        self.editor = DictationEditor(self.model, self)
        self.editor.highlight_changes = settings.highlight_changes
        self.editor.show_marks = settings.highlight_changes
        self.editor.italic = settings.document_italic
        self.editor.set_text_font(style.DOCUMENT_FONT, settings.font_size)

        self.engine = DictationEngine(settings, fake_asr=fake_asr, parent=self)
        self.engine.sentence.connect(self.on_sentence)
        self.engine.paragraph_break.connect(self.on_paragraph_break)
        self.engine.level.connect(self._on_level)
        self.engine.state.connect(self._on_engine_state)
        self.engine.error.connect(self._on_engine_error)
        self.engine.partial.connect(self._on_partial)
        self.engine.speaking.connect(self._on_speaking)
        self.engine.recording_saved.connect(lambda path: self.notify(f"Audio de diagnóstico guardado en {path}"))

        self.corrector = CorrectionQueue(self)
        self.corrector.started.connect(self._on_correction_started)
        self.corrector.finished.connect(self._on_correction_finished)
        self.corrector.status.connect(self._on_llm_status)
        self.model.paragraph_closed.connect(self._on_paragraph_closed)
        self.editor.show_diff.connect(self.show_diff)
        self.editor.revert.connect(self.model.revert)
        self.editor.recorrect.connect(self.model.request_recorrect)

        self._build_actions()
        self.canvas = _Canvas(self.editor, self)
        self.canvas.mic.clicked.connect(self.toggle_dictation)
        self.canvas.paragraph.clicked.connect(self.new_paragraph)
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addWidget(self.canvas, 1)
        self.setCentralWidget(root)
        self._refresh_status()

        self.model.modified_changed.connect(lambda _m: self._update_title())
        self.model.reset.connect(self._refresh_status)
        self.model.paragraph_added.connect(lambda *_: self._refresh_status())
        self._update_title()

        self._autosave = QTimer(self)
        self._autosave.timeout.connect(self.autosave)
        self._autosave.start(max(10, settings.autosave_s) * 1000)

        self.resize(QSize(1180, 860))
        self.setMinimumSize(QSize(860, 600))
        self.configure_llm()

    # -- construcción ---------------------------------------------------------------------------------------------

    def _action(self, text: str, slot, shortcut=None, checkable=False) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
            act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        act.setCheckable(checkable)
        act.triggered.connect(slot)
        self.addAction(act)  # los atajos funcionan aunque la acción no esté en ningún menú visible
        return act

    def _build_actions(self) -> None:
        self.act_dictate = self._action("Empezar o parar de hablar", self.toggle_dictation, "F9")
        self.act_paragraph = self._action("Nuevo párrafo", self.new_paragraph, "Ctrl+Return")
        self.act_new = self._action("Documento nuevo", self.file_new, QKeySequence.StandardKey.New)
        self.act_open = self._action("Abrir…", self.file_open, QKeySequence.StandardKey.Open)
        self.act_save = self._action("Guardar", self.file_save, QKeySequence.StandardKey.Save)
        self.act_save_as = self._action("Guardar con otro nombre…", self.file_save_as, "Ctrl+Shift+S")
        self.act_word = self._action("Guardar como documento de Word…", self.file_export_word, "Ctrl+E")
        self.act_print = self._action("Imprimir…", self.file_print, QKeySequence.StandardKey.Print)
        self.act_export = self._action("Exportar como texto o Markdown…", self.file_export)
        self.act_import = self._action("Importar un texto…", self.file_import)
        self.act_bigger = self._action("Letra más grande", lambda: self.change_font(+1), "Ctrl++")
        self.act_smaller = self._action("Letra más pequeña", lambda: self.change_font(-1), "Ctrl+-")
        self.act_settings = self._action("Ajustes…", self.open_settings, "Ctrl+,")
        self.act_glossary = self._action("Nombres y palabras especiales…", self.edit_glossary)
        self.act_correct_all = self._action("Volver a corregir todo el documento", self.recorrect_all)
        self.act_retry = self._action("Reintentar los párrafos sin corregir", self.retry_failed)
        self.act_help = self._action("Ver la explicación otra vez", lambda: self.run_onboarding(intro_only=True), "F1")
        self.act_quit = self._action("Salir", self.close, "Ctrl+Q")

    def _build_header(self) -> QWidget:
        header = _Header(self)
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(2)
        for icon, text, act in (
            (style.ICON_NEW, "Nuevo", self.act_new),
            (style.ICON_OPEN, "Abrir", self.act_open),
            (style.ICON_SAVE, "Guardar", self.act_save),
            (style.ICON_WORD, "Word", self.act_word),
            (style.ICON_PRINT, "Imprimir", self.act_print),
        ):
            b = IconButton(icon, text, act.text().rstrip("…") + f"  ({act.shortcut().toString(QKeySequence.SequenceFormat.NativeText)})")
            b.clicked.connect(act.trigger)
            row.addWidget(b)
        row.addStretch(1)
        self.mode_control = SegmentedControl(MODE_OPTIONS, header)
        self.mode_control.set_current(self.model.mode, animate=False)
        self.mode_control.changed.connect(self.set_mode)
        row.addWidget(self.mode_control, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        for size, text, act in ((12, "Letra −", self.act_smaller), (19, "Letra +", self.act_bigger)):
            b = IconButton("A", text, act.text(), glyph_font=style.display_font(size))
            b.clicked.connect(act.trigger)
            row.addWidget(b)
        self.more_button = IconButton(style.ICON_MORE, "Más", "Más opciones")
        self.more_button.clicked.connect(self._show_more_menu)
        row.addWidget(self.more_button)
        return header

    def more_menu(self) -> MenuPanel:
        """El panel de «Más»: pocas opciones, grandes y agrupadas."""
        panel = MenuPanel(self)
        recent = [f for f in self.settings.recent_files if Path(f).exists() and (not self.path or Path(f) != self.path)]
        if recent:
            panel.add_section("Abrir de nuevo")
            for f in recent[:4]:
                panel.add_row(style.ICON_RECENT, Path(f).stem, lambda f=f: self.maybe_save() and self.open_path(Path(f)))
        panel.add_section("Documento")
        panel.add_row(style.ICON_SAVE_AS, "Guardar con otro nombre…", self.act_save_as.trigger)
        panel.add_row(style.ICON_EXPORT, "Exportar como texto…", self.act_export.trigger)
        panel.add_row(style.ICON_IMPORT, "Importar un texto…", self.act_import.trigger)
        panel.add_section("Corrección")
        panel.add_row(style.ICON_BOOK, "Nombres y palabras especiales…", self.act_glossary.trigger)
        panel.add_row(style.ICON_HIGHLIGHT, "Marcar lo que se ha corregido", self._toggle_highlight,
                      toggle=self.settings.highlight_changes)
        if any(self._can_retry(p) for p in self.model.paragraphs):
            panel.add_row(style.ICON_WARNING, "Reintentar los párrafos sin corregir", self.act_retry.trigger)
        panel.add_row(style.ICON_REFRESH, "Volver a corregir todo", self.act_correct_all.trigger)
        panel.add_tiles([
            (style.ICON_HELP, "Ayuda", self.act_help.trigger),
            (style.ICON_SETTINGS, "Ajustes", self.act_settings.trigger),
            (style.ICON_QUIT, "Salir", self.act_quit.trigger),
        ])
        panel.add_note(self._llm_text())
        return panel

    def _show_more_menu(self) -> None:
        self.more_menu().popup_under(self.more_button)

    # -- avisos ---------------------------------------------------------------------------------------------------

    def notify(self, text: str, ms: int = 2600) -> None:
        self.canvas.toast.show_message(text, ms)

    def _refresh_status(self) -> None:
        state = self.canvas.mic.state
        if state == "loading":
            text = "Preparando el micrófono…"
        elif state == "listening":
            text = "Le escucho. Hable con normalidad."
        elif not any(p.text.strip() for p in self.model.paragraphs):
            text = "Pulse el botón y empiece a hablar"
        else:
            text = ""
        self.canvas.set_status(text)

    # -- dictado --------------------------------------------------------------------------------------------------

    def toggle_dictation(self) -> None:
        if self.engine.running:
            self.engine.stop()
            self.canvas.mic.set_state("idle")
        else:
            if not self.ensure_models():
                return
            self.engine.set_mode(self.model.mode)
            self.engine.start()
            self.canvas.mic.set_state("loading")
        self._refresh_status()

    def ensure_models(self) -> bool:
        """Sin los modelos de voz no se puede dictar: se abre el asistente para descargarlos."""
        if self.fake_asr:
            return True
        from dictador.engine import models_present

        if models_present(self.settings.models_path()):
            return True
        self.run_onboarding()
        return models_present(self.settings.models_path())

    def run_onboarding(self, intro_only: bool = False) -> None:
        from dictador.ui.onboarding import Onboarding

        Onboarding(self, intro_only=intro_only).exec()

    def new_paragraph(self) -> None:
        if self.engine.running:
            self.engine.request_paragraph_break()
        else:
            self.model.close_paragraph(correct=True)
        self.notify("Párrafo nuevo")

    def set_mode(self, mode: str) -> None:
        self.model.mode = mode
        self.engine.set_mode(mode)
        self.settings.mode = mode
        current = self.model.current()
        if current is not None:
            current.mode = mode
        self.mode_control.set_current(mode)
        self.model.set_modified(True)
        self.notify(dict((k, h) for k, _t, h in MODE_OPTIONS)[mode], 3500)

    def on_sentence(self, text: str) -> None:
        if self.suppress_dictation:
            return
        actions = commands.parse(text) if self.settings.voice_commands else [commands.Text(text)]
        for action in actions:
            if isinstance(action, commands.Text):
                mode = self.model.mode
                # En poesía cada frase es un verso; si llegan dos versos juntos, se separan por su puntuación.
                for piece in commands.split_verses(action.text) if mode == "poesia" else [action.text]:
                    self.model.append_sentence(piece, mode)
            elif isinstance(action, commands.NewParagraph):
                self.model.close_paragraph(correct=True)
                self.notify("Párrafo nuevo")
            elif isinstance(action, commands.DeleteLastSentence):
                done = self.model.delete_last_sentence()
                self.notify("He borrado la última frase" if done else "No hay ninguna frase que borrar")
            elif isinstance(action, commands.Title):
                self.model.add_title(action.text)
                self.notify("Título añadido")
        self._refresh_status()

    def on_paragraph_break(self) -> None:
        if not self.suppress_dictation:
            self.model.close_paragraph(correct=True)

    def _on_partial(self, text: str) -> None:
        # Una vista previa que llegue tarde, con el dictado ya parado, no se muestra.
        if not self.suppress_dictation:
            self.editor.set_partial(text if self.engine.running else "")

    def _on_level(self, value: float) -> None:
        self.canvas.mic.set_level(value)

    def _on_speaking(self, _speaking: bool) -> None:
        pass

    def _on_engine_state(self, state: str) -> None:
        mic = self.canvas.mic
        mic.set_state({"cargando": "loading", "escuchando": "listening", "parado": "idle"}[state])
        # Mientras se dicta, deshacer mezclaría el texto que llega con lo que escribe el usuario.
        self.editor.setUndoRedoEnabled(state == "parado")
        if state == "parado":
            self.editor.set_partial("")
        self._refresh_status()

    def _on_engine_error(self, message: str) -> None:
        low = message.lower()
        if "micr" in low or "portaudio" in low or "device" in low or "dispositivo" in low:
            title, text = "No oigo el micrófono", "Compruebe que el micrófono está conectado y vuelva a pulsar el botón."
        elif "transcrib" in low:
            self.notify("No he entendido un trozo; siga hablando.")
            return
        else:
            title, text = "No he podido empezar a escuchar", "Vuelva a intentarlo. Si sigue pasando, reinicie el programa."
        if not self.engine.running:
            tell(self, title, f"{text}\n\n(Detalle: {message})", warning=True)
        else:
            self.notify(title)

    # -- archivos -------------------------------------------------------------------------------------------------

    def _update_title(self) -> None:
        name = self.path.stem if self.path else "Documento nuevo"
        self.setWindowTitle(f"{'• ' if self.model.modified else ''}{name} — Dictador")

    def maybe_save(self) -> bool:
        if not self.model.modified or not any(p.text.strip() for p in self.model.paragraphs):
            return True
        choice = ask(
            self,
            "¿Quiere guardar lo que ha escrito?",
            "Si no lo guarda, lo escrito desde la última vez que guardó se perderá.",
            ["Guardar", "No guardar", "Cancelar"],
            icon=style.ICON_SAVE,
        )
        if choice == 0:
            return self.file_save()
        return choice == 1

    def file_new(self) -> None:
        if not self.maybe_save():
            return
        self.path = None
        self.model.load([], mode=self.model.mode)
        self._update_title()

    def file_open(self) -> None:
        if not self.maybe_save():
            return
        start = str(self.path.parent) if self.path else str(documents_dir())
        name, _ = QFileDialog.getOpenFileName(self, "Abrir un documento", start, FILE_FILTER)
        if name:
            self.open_path(Path(name))

    def open_path(self, path: Path) -> bool:
        try:
            paragraphs, mode, glossary = storage.load(path)
        except storage.StorageError as e:
            tell(self, "No se puede abrir ese documento", str(e), warning=True)
            return False
        self.path = path
        self.model.load(paragraphs, mode=mode, glossary=glossary)
        self.mode_control.set_current(mode, animate=False)
        self.engine.set_mode(mode)
        self.settings.add_recent(str(path))
        self._update_title()
        self.after_open()
        return True

    def after_open(self) -> None:
        """Al reabrir, lo que estaba pendiente vuelve a la cola."""
        for p in self.model.paragraphs:
            if p.status == "pending":
                self._on_paragraph_closed(p.id)

    def file_save(self) -> bool:
        if self.path is None:
            return self.file_save_as()
        return self._save_to(self.path)

    def file_save_as(self) -> bool:
        start = str(self.path) if self.path else str(documents_dir() / "Mi documento.dictador")
        name, _ = QFileDialog.getSaveFileName(self, "Guardar el documento", start, FILE_FILTER)
        if not name:
            return False
        path = Path(name)
        if path.suffix.lower() not in (storage.EXTENSION, ".dictado"):
            path = path.with_suffix(storage.EXTENSION)
        return self._save_to(path)

    def _save_to(self, path: Path) -> bool:
        self.editor.reconcile()
        try:
            storage.save(path, self.model.paragraphs, self.model.mode, self.model.glossary)
        except OSError as e:
            tell(self, "No se ha podido guardar", f"Pruebe a guardarlo en otra carpeta.\n\n(Detalle: {e})", warning=True)
            return False
        self.path = path
        self.model.set_modified(False)
        self.settings.add_recent(str(path))
        self._update_title()
        self.clear_recovery()
        self.notify("Guardado")
        return True

    def _export_base(self) -> Path:
        return self.path.with_suffix("") if self.path else documents_dir() / "Mi documento"

    def file_export_word(self) -> None:
        self.editor.reconcile()
        name, _ = QFileDialog.getSaveFileName(
            self, "Guardar como documento de Word", str(self._export_base()) + ".docx", "Documento de Word (*.docx)"
        )
        if not name:
            return
        path = Path(name) if name.lower().endswith(".docx") else Path(name + ".docx")
        try:
            storage.export(path, self.model.paragraphs)
        except (OSError, storage.StorageError) as e:
            tell(self, "No se ha podido guardar", f"¿Está ese documento abierto en Word? Ciérrelo y vuelva a probar.\n\n(Detalle: {e})", warning=True)
            return
        self.notify(f"Guardado como documento de Word: {path.name}", 3500)

    def file_export(self) -> None:
        self.editor.reconcile()
        name, chosen = QFileDialog.getSaveFileName(
            self, "Exportar", str(self._export_base()) + ".txt", "Texto (*.txt);;Markdown (*.md);;Documento de Word (*.docx)"
        )
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() not in (".docx", ".md", ".txt"):
            path = path.with_suffix({"Markdown": ".md", "Documento de Word": ".docx"}.get(chosen.split(" (")[0], ".txt"))
        try:
            storage.export(path, self.model.paragraphs)
        except (OSError, storage.StorageError) as e:
            tell(self, "No se ha podido exportar", str(e), warning=True)
            return
        self.notify(f"Exportado: {path.name}")

    def file_print(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        self.editor.reconcile()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Imprimir")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        self.printable_document().print_(printer)
        self.notify("Enviado a la impresora")

    def printable_document(self) -> QTextDocument:
        """El texto limpio, sin marcas ni lo que se está diciendo en ese momento, para imprimirlo."""
        parts = []
        for p in self.model.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            body = html.escape(text).replace("\n", "<br>")
            parts.append(f"<h1>{body}</h1>" if p.style == "title" else f"<p>{body}</p>")
        doc = QTextDocument()
        doc.setDefaultStyleSheet(
            "body { font-family: Georgia; font-size: 13pt; } p { margin-bottom: 10pt; line-height: 140%; }"
            " h1 { font-size: 20pt; }"
        )
        doc.setHtml("<body>" + "".join(parts) + "</body>")
        return doc

    def file_import(self) -> None:
        if not self.maybe_save():
            return
        name, _ = QFileDialog.getOpenFileName(self, "Importar un texto", str(documents_dir()), "Texto o Markdown (*.txt *.md)")
        if not name:
            return
        try:
            paragraphs = storage.import_text(name, mode=self.model.mode)
        except OSError as e:
            tell(self, "No se puede leer ese archivo", str(e), warning=True)
            return
        self.path = None
        self.model.load(paragraphs, mode=self.model.mode, glossary=[])
        self.model.set_modified(True)
        self._update_title()
        self.notify(f"Importados {len(paragraphs)} párrafos")

    def change_font(self, step: int) -> None:
        current = self.settings.font_size
        sizes = sorted(set(FONT_SIZES) | {current})
        i = sizes.index(current) + step
        if not 0 <= i < len(sizes):
            self.notify("Es el tamaño " + ("más grande" if step > 0 else "más pequeño"))
            return
        self.settings.font_size = sizes[i]
        self.editor.set_text_font(style.DOCUMENT_FONT, sizes[i])
        self.notify(f"Tamaño de letra: {sizes[i]}")

    # -- recuperación ---------------------------------------------------------------------------------------------

    @staticmethod
    def _recovery_files() -> tuple[Path, Path]:
        d = recovery_dir()
        return d / "recuperacion.dictador", d / "recuperacion.json"

    def autosave(self) -> None:
        if not self.model.modified:
            return
        data, meta = self._recovery_files()
        try:
            self.editor.reconcile()
            storage.save(data, self.model.paragraphs, self.model.mode, self.model.glossary)
            meta.write_text(json.dumps({"path": str(self.path) if self.path else None}), encoding="utf-8")
        except OSError:
            pass  # la copia de seguridad no debe molestar

    def clear_recovery(self) -> None:
        for f in self._recovery_files():
            f.unlink(missing_ok=True)

    def offer_recovery(self) -> None:
        data, meta = self._recovery_files()
        if not data.exists():
            return
        choice = ask(
            self,
            "¿Recuperamos lo que estaba escribiendo?",
            "La última vez el programa se cerró sin guardar. Podemos recuperar lo que estaba escribiendo.",
            ["Recuperar", "No, empezar de cero"],
            icon=style.ICON_IDEA,
        )
        if choice != 0:
            self.clear_recovery()
            return
        try:
            paragraphs, mode, glossary = storage.load(data)
            original = json.loads(meta.read_text(encoding="utf-8")).get("path") if meta.exists() else None
        except (storage.StorageError, OSError, ValueError) as e:
            tell(self, "No se ha podido recuperar", str(e), warning=True)
            return
        self.path = Path(original) if original else None
        self.model.load(paragraphs, mode=mode, glossary=glossary)
        self.mode_control.set_current(mode, animate=False)
        self.model.set_modified(True)
        self._update_title()
        self.after_open()

    # -- varios ---------------------------------------------------------------------------------------------------

    def _toggle_highlight(self, checked: bool) -> None:
        self.settings.highlight_changes = checked
        self.editor.highlight_changes = checked
        self.editor.show_marks = checked
        self.editor.refresh_formats()

    # -- corrección ------------------------------------------------------------------------------------------------

    def configure_llm(self) -> None:
        s = self.settings
        if self.fake_llm:
            from dictador.llm.client import FakeLLMClient

            self._stop_server()
            self.corrector.set_client(FakeLLMClient())
        elif s.managed_enabled:
            self._configure_managed()
        elif s.llm_base_url and s.llm_model:
            self._stop_server()
            from dictador.llm.client import LLMClient

            self.corrector.set_client(
                LLMClient(
                    s.llm_base_url, s.llm_model, s.llm_api_key, s.llm_timeout_s, s.llm_temperature, s.llm_disable_thinking
                )
            )
        else:
            self._stop_server()
            self.corrector.set_client(None)

    def _configure_managed(self) -> None:
        from dictador.llm.client import LLMClient
        from dictador.llm.managed import ManagedServer
        from dictador.models.download import builtin_model, builtin_server

        s = self.settings
        exe = s.managed_server_path or str(builtin_server(s.models_path()))
        gguf = s.managed_model_path or str(builtin_model(s.models_path()))
        if not Path(exe).is_file() or not Path(gguf).is_file():
            self._stop_server()
            self.corrector.set_client(None)
            self._on_llm_status("error", "Falta descargar el corrector (Más › Ajustes › Corrector).")
            return
        layers = s.managed_gpu_layers if s.managed_device == "gpu" else 0
        config = (exe, gguf, s.managed_port, layers, s.managed_ctx)
        if self.server is None or not self.server.same_config(*config):
            self._stop_server()
            self.server = ManagedServer(*config, log_path=localdata_dir() / "llama-server.log")
            try:
                self.server.start()
            except OSError as e:
                self.server = None
                self.corrector.set_client(None)
                self._on_llm_status("error", str(e))
                return
        server = self.server
        client = LLMClient(server.base_url, server.model_name, "", s.llm_timeout_s, s.llm_temperature, s.llm_disable_thinking)
        client.wait_until_ready = lambda: (server.ready.wait(), server.error)[1]
        client.is_ready = server.ready.is_set
        self.corrector.set_client(client)

    def _stop_server(self) -> None:
        if self.server is not None:
            self.server.stop()
            self.server = None

    def _glossary(self) -> list[str]:
        seen, terms = set(), []
        for t in self.settings.glossary + self.model.glossary:
            if t.lower() not in seen:
                seen.add(t.lower())
                terms.append(t)
        return terms

    def _on_paragraph_closed(self, pid: str) -> None:
        p = self.model.get(pid)
        if p is None or p.status != "pending":
            return
        if p.mode == "ninguno" or not self.corrector.configured:
            self.model.set_status(pid, "closed")
            return
        s = self.settings
        self.corrector.enqueue(
            CorrectionJob(
                pid=pid,
                raw=p.raw,
                mode=p.mode,
                context=self.model.context_before(pid, s.context_paragraphs),
                glossary=self._glossary(),
                max_distance=s.guard_max_distance,
                max_length_change=s.guard_max_length_change,
                max_removed=s.guard_max_removed,
            )
        )

    def _on_correction_started(self, pid: str) -> None:
        p = self.model.get(pid)
        if p is not None and p.status == "pending" and not p.user_edited:
            self.model.set_status(pid, "correcting")

    def _on_correction_finished(self, pid: str, raw: str, corrected, reason: str) -> None:
        p = self.model.get(pid)
        if p is None:
            return
        if p.status == "correcting":
            if self.model.apply_correction(pid, raw, corrected, reason) and corrected != raw:
                self.editor.flash(pid)
        elif p.status == "pending" and p.raw == raw and not self.corrector.configured:
            self.model.set_status(pid, "closed", reason)

    def _on_llm_status(self, state: str, detail: str) -> None:
        self._llm_state = (state, detail)

    def _llm_text(self) -> str:
        state, detail = self._llm_state
        return {
            "ok": "Corrector: listo" + (" (simulado)" if self.fake_llm else ""),
            "corrigiendo": "Corrector: corrigiendo…",
            "arrancando": "Corrector: preparándose…",
            "error": f"Corrector: no disponible ({detail})" if detail else "Corrector: no disponible",
        }.get(state, "Corrector: sin configurar")

    def show_diff(self, pid: str) -> None:
        p = self.model.get(pid)
        if p is not None and p.corrected is not None:
            DiffDialog(p.raw, p.corrected, self).exec()

    @staticmethod
    def _can_retry(p) -> bool:
        return p.status in ("rejected", "closed") and not p.user_edited and p.style != "title" and p.mode != "ninguno"

    def retry_failed(self) -> None:
        for p in list(self.model.paragraphs):
            if self._can_retry(p):
                self.model.request_recorrect(p.id)

    def recorrect_all(self) -> None:
        choice = ask(
            self,
            "¿Volver a corregir todo?",
            "Se volverán a corregir todos los párrafos dictados que no haya cambiado a mano, partiendo de lo que se "
            "oyó al dictar.",
            ["Corregir de nuevo", "Cancelar"],
        )
        if choice != 0:
            return
        for p in list(self.model.paragraphs):
            if not p.user_edited and p.style != "title" and p.mode != "ninguno":
                self.model.request_recorrect(p.id)

    def edit_glossary(self) -> None:
        dialog = GlossaryDialog(self.model.glossary, self)
        if dialog.exec():
            self.model.glossary = dialog.terms()
            self.model.set_modified(True)

    def open_settings(self) -> None:
        from dictador.ui.settings import SettingsDialog

        dialog = SettingsDialog(self.settings, self, fake_llm=self.fake_llm)
        if not dialog.exec():
            return
        new = dialog.result_settings()
        restart = self.engine.running and (
            new.input_device != self.settings.input_device
            or new.vad_threshold != self.settings.vad_threshold
            or new.models_dir != self.settings.models_dir
            or new.save_session_audio != self.settings.save_session_audio
        )
        for name, value in vars(new).items():
            setattr(self.settings, name, value)
        self.save_settings()
        self.editor.italic = self.settings.document_italic
        self.editor.set_text_font(style.DOCUMENT_FONT, self.settings.font_size)
        apply_theme(self.settings.theme)
        self._autosave.start(max(10, self.settings.autosave_s) * 1000)
        self.engine.set_mode(self.model.mode)  # las pausas se aplican en caliente
        self.configure_llm()
        if restart:
            self.notify("Los cambios del micrófono se aplican al volver a pulsar «Empezar a hablar».", 4000)

    def save_settings(self) -> None:
        try:
            self.settings.save()
        except OSError:
            pass

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.maybe_save():
            event.ignore()
            return
        self.engine.shutdown()
        self.corrector.shutdown()
        self._stop_server()
        self.clear_recovery()
        self.save_settings()
        event.accept()
