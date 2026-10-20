"""Ventana principal: barra de dictado, editor, menús, guardado y autoguardado."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
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

from dictado import commands
from dictado.config import MODE_LABELS, MODES, Settings, localdata_dir, recovery_dir
from dictado.doc import storage
from dictado.doc.model import DocumentModel
from dictado.engine import DictationEngine
from dictado.llm.queue import CorrectionJob, CorrectionQueue
from dictado.ui.dialogs import DiffDialog, GlossaryDialog
from dictado.ui.editor import DictationEditor
from dictado.ui.theme import THEME_LABELS, THEMES, apply_theme

FILE_FILTER = "Proyecto de Dictado (*.dictado)"


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, fake_asr: bool = False, fake_llm: bool = False):
        super().__init__()
        self.settings = settings
        self.fake_asr = fake_asr
        self.fake_llm = fake_llm
        self.path: Path | None = None
        self.server = None  # llama-server propio (modo gestionado)

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
        self.engine.partial.connect(self._on_partial)
        self.engine.recording_saved.connect(
            lambda path: self.statusBar().showMessage(f"Audio de diagnóstico guardado en {path}", 10_000)
        )

        self.corrector = CorrectionQueue(self)
        self.corrector.started.connect(self._on_correction_started)
        self.corrector.finished.connect(self._on_correction_finished)
        self.corrector.status.connect(self._on_llm_status)
        self.model.paragraph_closed.connect(self._on_paragraph_closed)
        self.editor.show_diff.connect(self.show_diff)
        self.editor.revert.connect(self.model.revert)
        self.editor.recorrect.connect(self.model.request_recorrect)

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
        self.configure_llm()

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
        self.act_dictate = self._action("● Dictar", self.toggle_dictation, "F9", checkable=True)
        self.act_dictate.setToolTip("Empezar o pausar el dictado (F9)")
        self.act_paragraph = self._action("Nuevo párrafo", self.new_paragraph, "Ctrl+Return")
        self.act_paragraph.setToolTip("Cerrar el párrafo actual (Ctrl+Intro)")
        self.act_new = self._action("&Nuevo", self.file_new, QKeySequence.StandardKey.New)
        self.act_open = self._action("&Abrir…", self.file_open, QKeySequence.StandardKey.Open)
        self.act_save = self._action("&Guardar", self.file_save, QKeySequence.StandardKey.Save)
        self.act_save_as = self._action("Guardar &como…", self.file_save_as, "Ctrl+Shift+S")
        self.act_quit = self._action("&Salir", self.close, "Ctrl+Q")
        self.act_export = self._action("&Exportar…", self.file_export, "Ctrl+E")
        self.act_import = self._action("&Importar texto…", self.file_import)
        self.act_highlight = self._action("&Resaltar cambios del corrector", self._toggle_highlight, checkable=True)
        self.act_highlight.setChecked(self.settings.highlight_changes)
        self.act_settings = self._action("&Ajustes…", self.open_settings, "Ctrl+,")
        self.act_models = self._action("&Modelos…", self.open_models)
        self.act_glossary = self._action("&Glosario del documento…", self.edit_glossary)
        self.act_correct_all = self._action("&Volver a corregir todo el documento", self.recorrect_all)
        self.act_retry = self._action("&Reintentar los párrafos sin corregir", self.retry_failed)

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
                button.setMinimumWidth(90)
                button.setStyleSheet(
                    "QToolButton { font-weight: bold; padding: 3px 10px; }"
                    "QToolButton:checked { background: #c62f2f; color: white; border-radius: 4px; }"
                )

    def _build_menus(self) -> None:
        menu = self.menuBar()
        self.file_menu = menu.addMenu("&Archivo")
        self.file_menu.addActions([self.act_new, self.act_open])
        self.recent_menu = self.file_menu.addMenu("Abrir &reciente")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self.file_menu.addSeparator()
        self.file_menu.addActions([self.act_save, self.act_save_as])
        self.file_menu.addSeparator()
        self.file_menu.addActions([self.act_import, self.act_export])
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.act_quit)

        self.dictate_menu = menu.addMenu("&Dictado")
        self.dictate_menu.addActions([self.act_dictate, self.act_paragraph])

        self.doc_menu = menu.addMenu("D&ocumento")
        self.doc_menu.addActions([self.act_glossary])
        self.doc_menu.addSeparator()
        self.doc_menu.addActions([self.act_retry, self.act_correct_all])

        self.view_menu = menu.addMenu("&Ver")
        self.view_menu.addAction(self.act_highlight)
        theme_menu = self.view_menu.addMenu("&Tema")
        self.theme_group = QActionGroup(self)
        for key in THEMES:
            act = theme_menu.addAction(THEME_LABELS[key])
            act.setCheckable(True)
            act.setData(key)
            act.setChecked(key == self.settings.theme)
            self.theme_group.addAction(act)
        self.theme_group.triggered.connect(lambda act: self.set_theme(act.data()))

        self.tools_menu = menu.addMenu("&Herramientas")
        self.tools_menu.addActions([self.act_models, self.act_settings])

    # -- dictado --------------------------------------------------------------------------------------------------

    def toggle_dictation(self) -> None:
        if self.engine.running:
            self.engine.stop()
            self.act_dictate.setChecked(False)
            self.act_dictate.setText("● Dictar")
        else:
            if not self.ensure_models():
                self.act_dictate.setChecked(False)
                return
            self.engine.set_mode(self.model.mode)
            self.engine.start()
            self.act_dictate.setChecked(True)
            self.act_dictate.setText("❚❚ Pausa")

    def ensure_models(self) -> bool:
        """Hook para el asistente de primer arranque (fase 4). Sin modelos no se puede dictar."""
        if self.fake_asr:
            return True
        from dictado.engine import models_present

        if models_present(self.settings.models_path()):
            return True
        self.open_models(first_run=True)
        return models_present(self.settings.models_path())

    def open_models(self, first_run: bool = False) -> None:
        from dictado.engine import models_present
        from dictado.ui.models_dialog import ModelsDialog

        from dictado.models.download import LLM_PACKS, pack_present

        s = self.settings
        had_voice = models_present(s.models_path())
        had_llm = all(pack_present(s.models_path(), p) for p in LLM_PACKS)
        dialog = ModelsDialog(s.models_path(), self, first_run=first_run, include_llm=s.managed_enabled)
        dialog.exec()
        if not had_voice and models_present(s.models_path()) and not self.fake_asr:
            self.engine.preload()
        if not had_llm and all(pack_present(s.models_path(), p) for p in LLM_PACKS):
            if not s.managed_enabled and not s.llm_model:
                s.managed_enabled = True  # recién descargado y sin otro corrector: se usa el integrado
            if s.managed_enabled:
                self.configure_llm()

    def new_paragraph(self) -> None:
        if self.engine.running:
            self.engine.request_paragraph_break()
        else:
            self.model.close_paragraph(correct=True)

    def on_sentence(self, text: str) -> None:
        actions = commands.parse(text) if self.settings.voice_commands else [commands.Text(text)]
        for action in actions:
            if isinstance(action, commands.Text):
                mode = self.model.mode
                # En poesía cada frase es un verso; si llegan dos versos juntos, se separan por su puntuación.
                for piece in commands.split_verses(action.text) if mode == "poesia" else [action.text]:
                    self.model.append_sentence(piece, mode)
            elif isinstance(action, commands.NewParagraph):
                self.model.close_paragraph(correct=True)
                self.statusBar().showMessage("Comando: nuevo párrafo", 2500)
            elif isinstance(action, commands.DeleteLastSentence):
                done = self.model.delete_last_sentence()
                self.statusBar().showMessage("Comando: frase borrada" if done else "No hay frase que borrar", 2500)
            elif isinstance(action, commands.Title):
                self.model.add_title(action.text)
                self.statusBar().showMessage("Comando: título", 2500)

    def on_paragraph_break(self) -> None:
        self.model.close_paragraph(correct=True)

    def _on_partial(self, text: str) -> None:
        # Una vista previa que llegue tarde, con el dictado ya parado, no se muestra.
        self.editor.set_partial(text if self.engine.running else "")

    def _on_mode_changed(self, _index: int) -> None:
        mode = self.mode_combo.currentData()
        self.model.mode = mode
        self.engine.set_mode(mode)
        self.settings.mode = mode
        current = self.model.current()
        if current is not None:
            current.mode = mode
        self.model.set_modified(True)

    def _on_level(self, value: float) -> None:
        self.level_bar.setValue(int(value * 100))

    def _on_engine_state(self, state: str) -> None:
        self.state_label.setText({"cargando": "Cargando…", "escuchando": "Escuchando", "parado": "Parado"}[state])
        # Mientras se dicta, deshacer mezclaría el texto que llega con lo que escribe el usuario.
        self.editor.setUndoRedoEnabled(state == "parado")
        if state == "parado":
            self.editor.set_partial("")
        if state == "parado" and self.act_dictate.isChecked():
            self.act_dictate.setChecked(False)
            self.act_dictate.setText("● Dictar")

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

    def file_export(self) -> None:
        self.editor.reconcile()
        base = self.path.with_suffix("") if self.path else Path("documento")
        name, chosen = QFileDialog.getSaveFileName(
            self,
            "Exportar",
            str(base) + ".docx",
            "Documento de Word (*.docx);;Markdown (*.md);;Texto (*.txt)",
        )
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() not in (".docx", ".md", ".txt"):
            path = path.with_suffix({"Markdown": ".md", "Texto": ".txt"}.get(chosen.split(" (")[0], ".docx"))
        pending = sum(p.status in ("pending", "correcting") for p in self.model.paragraphs)
        try:
            storage.export(path, self.model.paragraphs)
        except (OSError, storage.StorageError) as e:
            QMessageBox.critical(self, "Exportar", f"No se pudo exportar:\n{e}")
            return
        note = f" ({pending} párrafo(s) aún sin corregir)" if pending else ""
        self.statusBar().showMessage(f"Exportado a {path}{note}", 6000)

    def file_import(self) -> None:
        if not self.maybe_save():
            return
        name, _ = QFileDialog.getOpenFileName(self, "Importar texto", "", "Texto o Markdown (*.txt *.md)")
        if not name:
            return
        try:
            paragraphs = storage.import_text(name, mode=self.model.mode)
        except OSError as e:
            QMessageBox.critical(self, "Importar", f"No se pudo leer el archivo:\n{e}")
            return
        self.path = None
        self.model.load(paragraphs, mode=self.model.mode, glossary=[])
        self.model.set_modified(True)
        self._update_title()
        self.statusBar().showMessage(
            f"Importados {len(paragraphs)} párrafos. El dictado continúa al final; "
            "los párrafos importados no se corrigen salvo que lo pidas.",
            8000,
        )

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

    def set_theme(self, theme: str) -> None:
        self.settings.theme = theme
        apply_theme(theme)
        for act in self.theme_group.actions():
            act.setChecked(act.data() == theme)

    def _toggle_highlight(self, checked: bool) -> None:
        self.settings.highlight_changes = checked
        self.editor.highlight_changes = checked
        self.editor.refresh_formats()

    # -- corrección ------------------------------------------------------------------------------------------------

    def configure_llm(self) -> None:
        s = self.settings
        if self.fake_llm:
            from dictado.llm.client import FakeLLMClient

            self._stop_server()
            self.corrector.set_client(FakeLLMClient())
        elif s.managed_enabled:
            self._configure_managed()
        elif s.llm_base_url and s.llm_model:
            self._stop_server()
            from dictado.llm.client import LLMClient

            self.corrector.set_client(
                LLMClient(
                    s.llm_base_url, s.llm_model, s.llm_api_key, s.llm_timeout_s, s.llm_temperature, s.llm_disable_thinking
                )
            )
        else:
            self._stop_server()
            self.corrector.set_client(None)

    def _configure_managed(self) -> None:
        from dictado.llm.client import LLMClient
        from dictado.llm.managed import ManagedServer

        from dictado.models.download import builtin_model, builtin_server

        s = self.settings
        exe = s.managed_server_path or str(builtin_server(s.models_path()))
        gguf = s.managed_model_path or str(builtin_model(s.models_path()))
        if not Path(exe).is_file() or not Path(gguf).is_file():
            self._stop_server()
            self.corrector.set_client(None)
            self._on_llm_status("error", "Faltan los archivos del corrector integrado: descárgalos en Herramientas › Modelos.")
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
                self.statusBar().showMessage(f"Modo gestionado: {e}", 8000)
                return
        server = self.server
        client = LLMClient(
            server.base_url, server.model_name, "", s.llm_timeout_s, s.llm_temperature, s.llm_disable_thinking
        )
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
            self.model.apply_correction(pid, raw, corrected, reason)
        elif p.status == "pending" and p.raw == raw and not self.corrector.configured:
            self.model.set_status(pid, "closed", reason)
        if corrected is None and reason:
            self.statusBar().showMessage(reason, 6000)

    def _on_llm_status(self, state: str, detail: str) -> None:
        if state == "ok":
            text, color, tip = "LLM: conectado", "#3a9a4a", self.settings.llm_model
        elif state == "corrigiendo":
            text = f"LLM: corrigiendo ({detail})" if detail not in ("", "0", "1") else "LLM: corrigiendo"
            color, tip = "#3a7ae0", ""
        elif state == "error":
            text, color, tip = "LLM: error", "#d0782a", detail
        elif state == "arrancando":
            text, color, tip = "LLM: arrancando servidor…", "#3a7ae0", "Cargando el modelo en llama-server"
        else:
            text, color, tip = "LLM: sin configurar", "#888888", "Configura el corrector en Herramientas › Ajustes."
        if self.fake_llm and state == "ok":
            text += " (simulado)"
        self.llm_label.setText(f'<span style="color:{color}">●</span> {text}')
        self.llm_label.setToolTip(tip)

    def show_diff(self, pid: str) -> None:
        p = self.model.get(pid)
        if p is not None and p.corrected is not None:
            DiffDialog(p.raw, p.corrected, self).exec()

    def retry_failed(self) -> None:
        for p in list(self.model.paragraphs):
            if p.status in ("rejected", "closed") and not p.user_edited and p.style != "title" and p.mode != "ninguno":
                self.model.request_recorrect(p.id)

    def recorrect_all(self) -> None:
        answer = QMessageBox.question(
            self,
            "Volver a corregir",
            "Se volverán a corregir todos los párrafos dictados que no hayas editado a mano, "
            "partiendo del texto original de Parakeet. ¿Seguir?",
        )
        if answer != QMessageBox.StandardButton.Yes:
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
        from dictado.ui.settings import SettingsDialog

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
        try:
            self.settings.save()
        except OSError as e:
            QMessageBox.warning(self, "Ajustes", f"No se pudieron guardar los ajustes: {e}")
        self.editor.set_text_font("Georgia", self.settings.font_size)
        self.set_theme(self.settings.theme)
        self._autosave.start(max(10, self.settings.autosave_s) * 1000)
        self.engine.set_mode(self.model.mode)  # las pausas se aplican en caliente
        self.configure_llm()
        if restart:
            self.statusBar().showMessage("Los cambios del micrófono se aplican al volver a dictar.", 6000)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.maybe_save():
            event.ignore()
            return
        self.engine.shutdown()
        self.corrector.shutdown()
        self._stop_server()
        self.clear_recovery()
        try:
            self.settings.save()
        except OSError:
            pass
        event.accept()
