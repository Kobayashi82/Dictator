"""Ventana principal: barra de dictado, editor, menús, guardado y autoguardado."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QToolBar,
    QToolButton,
    QWidget,
    QSizePolicy,
)

from dictado.config import MODE_LABELS, MODES, Settings, recovery_dir
from dictado.doc import storage
from dictado.doc.model import DocumentModel
from dictado.engine import DictationEngine
from dictado.ui.editor import DictationEditor

FILE_FILTER = "Proyecto de Dictado (*.dictado)"


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, fake_asr: bool = False, fake_llm: bool = False):
        super().__init__()
        self.settings = settings
        self.fake_asr = fake_asr
        self.fake_llm = fake_llm
        self.path: Path | None = None

        self.model = DocumentModel(self)
        self.model.mode = settings.mode
        self.editor = DictationEditor(self.model, self)
        self.editor.highlight_changes = settings.highlight_changes
        self.editor.set_text_font("Georgia", settings.font_size)
        self.setCentralWidget(self.editor)

        self.engine = DictationEngine(settings, fake_asr=fake_asr, parent=self)
        self.engine.sentence.connect(self.on_sentence)
        self.engine.paragraph_break.connect(self.on_paragraph_break)
        self.engine.level.connect(self._on_level)
        self.engine.state.connect(self._on_engine_state)
        self.engine.error.connect(self._on_engine_error)
        self.engine.asr_busy.connect(self._on_asr_busy)

        self._build_actions()
        self._build_toolbar()
        self._build_menus()
        self.statusBar()

        self.model.modified_changed.connect(lambda _m: self._update_title())
        self._update_title()

        self._autosave = QTimer(self)
        self._autosave.timeout.connect(self.autosave)
        self._autosave.start(max(10, settings.autosave_s) * 1000)

        self.resize(QSize(980, 760))

    # -- construcción ---------------------------------------------------------------------------------------------

    def _action(self, text: str, slot, shortcut=None, checkable=False) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
            act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        act.setCheckable(checkable)
        act.triggered.connect(slot)
        return act

    def _build_actions(self) -> None:
        self.act_dictate = self._action("Dictar", self.toggle_dictation, "F9", checkable=True)
        self.act_dictate.setToolTip("Empezar o pausar el dictado (F9)")
        self.act_paragraph = self._action("Nuevo párrafo", self.new_paragraph, "Ctrl+Return")
        self.act_paragraph.setToolTip("Cerrar el párrafo actual (Ctrl+Intro)")
        self.act_new = self._action("&Nuevo", self.file_new, QKeySequence.StandardKey.New)
        self.act_open = self._action("&Abrir…", self.file_open, QKeySequence.StandardKey.Open)
        self.act_save = self._action("&Guardar", self.file_save, QKeySequence.StandardKey.Save)
        self.act_save_as = self._action("Guardar &como…", self.file_save_as, "Ctrl+Shift+S")
        self.act_quit = self._action("&Salir", self.close, "Ctrl+Q")
        self.act_highlight = self._action("&Resaltar cambios del corrector", self._toggle_highlight, checkable=True)
        self.act_highlight.setChecked(self.settings.highlight_changes)

    def _build_toolbar(self) -> None:
        bar = QToolBar("Dictado", self)
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(bar)

        bar.addAction(self.act_dictate)
        bar.addSeparator()
        bar.addWidget(QLabel(" Modo: "))
        self.mode_combo = QComboBox(self)
        for m in MODES:
            self.mode_combo.addItem(MODE_LABELS[m], m)
        self.mode_combo.setCurrentIndex(MODES.index(self.model.mode))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        bar.addWidget(self.mode_combo)
        bar.addSeparator()
        bar.addAction(self.act_paragraph)

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        self.state_label = QLabel("Parado", self)
        self.state_label.setMinimumWidth(110)
        bar.addWidget(self.state_label)
        self.level_bar = QProgressBar(self)
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedSize(90, 10)
        self.level_bar.setToolTip("Nivel del micrófono")
        bar.addWidget(self.level_bar)
        self.llm_label = QLabel("", self)
        self.llm_label.setContentsMargins(12, 0, 6, 0)
        bar.addWidget(self.llm_label)

        for button in bar.findChildren(QToolButton):
            if button.defaultAction() is self.act_dictate:
                button.setMinimumWidth(80)

    def _build_menus(self) -> None:
        menu = self.menuBar()
        self.file_menu = menu.addMenu("&Archivo")
        self.file_menu.addActions([self.act_new, self.act_open])
        self.recent_menu = self.file_menu.addMenu("Abrir &reciente")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self.file_menu.addSeparator()
        self.file_menu.addActions([self.act_save, self.act_save_as])
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.act_quit)

        self.dictate_menu = menu.addMenu("&Dictado")
        self.dictate_menu.addActions([self.act_dictate, self.act_paragraph])

        self.view_menu = menu.addMenu("&Ver")
        self.view_menu.addAction(self.act_highlight)

    # -- dictado --------------------------------------------------------------------------------------------------

    def toggle_dictation(self) -> None:
        if self.engine.running:
            self.engine.stop()
            self.act_dictate.setChecked(False)
            self.act_dictate.setText("Dictar")
        else:
            if not self.ensure_models():
                self.act_dictate.setChecked(False)
                return
            self.engine.start()
            self.act_dictate.setChecked(True)
            self.act_dictate.setText("Pausa")

    def ensure_models(self) -> bool:
        """Hook para el asistente de primer arranque (fase 4). Sin modelos no se puede dictar."""
        if self.fake_asr:
            return True
        from dictado.engine import models_present

        if models_present(self.settings.models_path()):
            return True
        QMessageBox.warning(
            self,
            "Faltan modelos",
            f"No se encuentran los modelos de voz en:\n{self.settings.models_path()}\n\n"
            "Descárgalos desde Herramientas › Modelos de voz.",
        )
        return False

    def new_paragraph(self) -> None:
        if self.engine.running:
            self.engine.request_paragraph_break()
        else:
            self.model.close_paragraph(correct=True)

    def on_sentence(self, text: str) -> None:
        self.model.append_sentence(text, self.model.mode)

    def on_paragraph_break(self) -> None:
        self.model.close_paragraph(correct=True)

    def _on_mode_changed(self, _index: int) -> None:
        mode = self.mode_combo.currentData()
        self.model.mode = mode
        self.settings.mode = mode
        current = self.model.current()
        if current is not None:
            current.mode = mode
        self.model.set_modified(True)

    def _on_level(self, value: float) -> None:
        self.level_bar.setValue(int(value * 100))

    def _on_engine_state(self, state: str) -> None:
        self.state_label.setText({"cargando": "Cargando…", "escuchando": "Escuchando", "parado": "Parado"}[state])
        if state == "parado" and self.act_dictate.isChecked():
            self.act_dictate.setChecked(False)
            self.act_dictate.setText("Dictar")

    def _on_engine_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 10_000)
        if not self.engine.running:
            QMessageBox.critical(self, "Dictado", message)

    def _on_asr_busy(self, pending: int) -> None:
        if self.engine.running:
            self.state_label.setText(f"Transcribiendo ({pending})" if pending > 1 else "Escuchando")

    # -- archivos -------------------------------------------------------------------------------------------------

    def _update_title(self) -> None:
        name = self.path.name if self.path else "Sin título"
        self.setWindowTitle(f"{'*' if self.model.modified else ''}{name} — Dictado")

    def maybe_save(self) -> bool:
        if not self.model.modified:
            return True
        answer = QMessageBox.question(
            self,
            "Dictado",
            "El documento tiene cambios sin guardar. ¿Guardarlos?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.file_save()
        return answer == QMessageBox.StandardButton.Discard

    def file_new(self) -> None:
        if not self.maybe_save():
            return
        self.path = None
        self.model.load([], mode=self.model.mode)
        self._update_title()

    def file_open(self) -> None:
        if not self.maybe_save():
            return
        start = str(self.path.parent) if self.path else ""
        name, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", start, FILE_FILTER)
        if name:
            self.open_path(Path(name))

    def open_path(self, path: Path) -> bool:
        try:
            paragraphs, mode, glossary = storage.load(path)
        except storage.StorageError as e:
            QMessageBox.critical(self, "Abrir", str(e))
            return False
        self.path = path
        self.model.load(paragraphs, mode=mode, glossary=glossary)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(MODES.index(mode) if mode in MODES else 0)
        self.mode_combo.blockSignals(False)
        self.settings.add_recent(str(path))
        self._update_title()
        self.after_open()
        return True

    def after_open(self) -> None:
        """Hook: al reabrir, lo que estaba pendiente vuelve a la cola (fase 2)."""

    def file_save(self) -> bool:
        if self.path is None:
            return self.file_save_as()
        return self._save_to(self.path)

    def file_save_as(self) -> bool:
        start = str(self.path) if self.path else "documento.dictado"
        name, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", start, FILE_FILTER)
        if not name:
            return False
        path = Path(name)
        if path.suffix.lower() != storage.EXTENSION:
            path = path.with_suffix(storage.EXTENSION)
        return self._save_to(path)

    def _save_to(self, path: Path) -> bool:
        self.editor.reconcile()
        try:
            storage.save(path, self.model.paragraphs, self.model.mode, self.model.glossary)
        except OSError as e:
            QMessageBox.critical(self, "Guardar", f"No se pudo guardar:\n{e}")
            return False
        self.path = path
        self.model.set_modified(False)
        self.settings.add_recent(str(path))
        self._update_title()
        self.clear_recovery()
        self.statusBar().showMessage(f"Guardado en {path}", 4000)
        return True

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        files = [f for f in self.settings.recent_files if Path(f).exists()]
        if not files:
            self.recent_menu.addAction("(vacío)").setEnabled(False)
        for f in files:
            self.recent_menu.addAction(f, lambda f=f: self.maybe_save() and self.open_path(Path(f)))

    # -- recuperación ---------------------------------------------------------------------------------------------

    @staticmethod
    def _recovery_files() -> tuple[Path, Path]:
        d = recovery_dir()
        return d / "recuperacion.dictado", d / "recuperacion.json"

    def autosave(self) -> None:
        if not self.model.modified:
            return
        data, meta = self._recovery_files()
        try:
            self.editor.reconcile()
            storage.save(data, self.model.paragraphs, self.model.mode, self.model.glossary)
            meta.write_text(json.dumps({"path": str(self.path) if self.path else None}), encoding="utf-8")
        except OSError as e:
            self.statusBar().showMessage(f"No se pudo autoguardar: {e}", 5000)

    def clear_recovery(self) -> None:
        for f in self._recovery_files():
            f.unlink(missing_ok=True)

    def offer_recovery(self) -> None:
        data, meta = self._recovery_files()
        if not data.exists():
            return
        answer = QMessageBox.question(
            self,
            "Recuperar",
            "Dictado no se cerró bien la última vez. ¿Recuperar el documento autoguardado?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.clear_recovery()
            return
        try:
            paragraphs, mode, glossary = storage.load(data)
            original = json.loads(meta.read_text(encoding="utf-8")).get("path") if meta.exists() else None
        except (storage.StorageError, OSError, ValueError) as e:
            QMessageBox.warning(self, "Recuperar", f"No se pudo recuperar: {e}")
            return
        self.path = Path(original) if original else None
        self.model.load(paragraphs, mode=mode, glossary=glossary)
        self.model.set_modified(True)
        self._update_title()
        self.after_open()

    # -- varios ---------------------------------------------------------------------------------------------------

    def _toggle_highlight(self, checked: bool) -> None:
        self.settings.highlight_changes = checked
        self.editor.highlight_changes = checked
        self.editor.refresh_formats()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.maybe_save():
            event.ignore()
            return
        self.engine.shutdown()
        self.clear_recovery()
        try:
            self.settings.save()
        except OSError:
            pass
        event.accept()
