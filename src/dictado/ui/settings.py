"""Diálogo de ajustes."""

from __future__ import annotations

import threading
from dataclasses import replace

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dictado.config import MODE_LABELS, MODES, Settings, default_models_dir


class _Probe(QObject):
    done = Signal(object, str)  # lista de modelos | None, mensaje


def _row(*widgets) -> QWidget:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        layout.addWidget(x)
    return w


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None, fake_llm: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.setMinimumWidth(560)
        self._original = settings
        self.fake_llm = fake_llm
        s = settings

        tabs = QTabWidget(self)
        tabs.addTab(self._general_tab(s), "General")
        tabs.addTab(self._dictation_tab(s), "Dictado")
        tabs.addTab(self._llm_tab(s), "Corrector (LLM)")
        tabs.addTab(self._glossary_tab(s), "Glosario")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        self._probe = _Probe(self)
        self._probe.done.connect(self._on_probe)

    # -- pestañas -------------------------------------------------------------------------------------------------

    def _general_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.mode = QComboBox()
        for m in MODES:
            self.mode.addItem(MODE_LABELS[m], m)
        self.mode.setCurrentIndex(MODES.index(s.mode))
        form.addRow("Modo por defecto:", self.mode)

        from dictado.ui.theme import THEME_LABELS, THEMES

        self.theme = QComboBox()
        for key in THEMES:
            self.theme.addItem(THEME_LABELS[key], key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.theme)))
        form.addRow("Tema:", self.theme)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 36)
        self.font_size.setValue(s.font_size)
        form.addRow("Tamaño de letra:", self.font_size)

        self.autosave = QSpinBox()
        self.autosave.setRange(10, 3600)
        self.autosave.setSuffix(" s")
        self.autosave.setValue(s.autosave_s)
        form.addRow("Autoguardado cada:", self.autosave)

        self.models_dir = QLineEdit(s.models_dir)
        self.models_dir.setPlaceholderText(str(default_models_dir()))
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._browse_models)
        form.addRow("Carpeta de modelos:", _row(self.models_dir, browse))
        return w

    def _dictation_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.device = QComboBox()
        self.device.addItem("Predeterminado del sistema", "")
        try:
            from dictado.audio.capture import list_input_devices

            for name in list_input_devices():
                self.device.addItem(name, name)
        except Exception as e:  # noqa: BLE001
            self.device.addItem(f"(no se pudieron listar: {e})", "")
        i = self.device.findData(s.input_device)
        self.device.setCurrentIndex(max(0, i))
        form.addRow("Micrófono:", self.device)

        self.short_pause = QSpinBox()
        self.short_pause.setRange(300, 3000)
        self.short_pause.setSingleStep(100)
        self.short_pause.setSuffix(" ms")
        self.short_pause.setValue(s.short_pause_ms)
        form.addRow("Pausa que cierra la frase:", self.short_pause)

        self.long_pause = QSpinBox()
        self.long_pause.setRange(1000, 10000)
        self.long_pause.setSingleStep(250)
        self.long_pause.setSuffix(" ms")
        self.long_pause.setValue(s.long_pause_ms)
        form.addRow("Pausa que cierra el párrafo:", self.long_pause)

        self.verse_pause = QSpinBox()
        self.verse_pause.setRange(150, 2000)
        self.verse_pause.setSingleStep(50)
        self.verse_pause.setSuffix(" ms")
        self.verse_pause.setValue(s.poetry_verse_pause_ms)
        form.addRow("Poesía · pausa que cierra el verso:", self.verse_pause)

        self.stanza_pause = QSpinBox()
        self.stanza_pause.setRange(500, 10000)
        self.stanza_pause.setSingleStep(100)
        self.stanza_pause.setSuffix(" ms")
        self.stanza_pause.setValue(s.poetry_stanza_pause_ms)
        form.addRow("Poesía · pausa que cierra la estrofa:", self.stanza_pause)

        self.live_text = QCheckBox("Mostrar el texto mientras hablo (antes de que se cierre la frase)")
        self.live_text.setChecked(s.live_text)
        form.addRow(self.live_text)

        self.vad_threshold = QDoubleSpinBox()
        self.vad_threshold.setRange(0.1, 0.95)
        self.vad_threshold.setSingleStep(0.05)
        self.vad_threshold.setValue(s.vad_threshold)
        self.vad_threshold.setToolTip("Más alto: necesita voz más clara para empezar una frase (menos ruido).")
        form.addRow("Sensibilidad de la VAD:", self.vad_threshold)

        self.voice_commands = QCheckBox("Reconocer comandos de voz («punto y aparte», «borra la última frase»…)")
        self.voice_commands.setChecked(s.voice_commands)
        form.addRow(self.voice_commands)

        self.save_audio = QCheckBox("Guardar el audio de cada sesión para diagnóstico (en %LOCALAPPDATA%\\Dictado\\diagnostico)")
        self.save_audio.setChecked(s.save_session_audio)
        form.addRow(self.save_audio)
        return w

    def _llm_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        top = QFormLayout()
        self.source = QComboBox()
        self.source.addItem("Integrado: Qwen3.5 2B en este equipo", True)
        self.source.addItem("Servidor externo (Ollama, llama-swap, LM Studio, remoto…)", False)
        self.source.setCurrentIndex(0 if s.managed_enabled else 1)
        top.addRow("Corrector:", self.source)
        outer.addLayout(top)

        # -- integrado --
        self.managed = QGroupBox("Corrector integrado")
        mform = QFormLayout(self.managed)
        self.llm_device = QComboBox()
        self.llm_device.addItem("CPU (en la RAM)", "cpu")
        self.llm_device.addItem("GPU (Vulkan)", "gpu")
        self.llm_device.setCurrentIndex(1 if s.managed_device == "gpu" else 0)
        self.gpu_layers = QSpinBox()
        self.gpu_layers.setRange(1, 999)
        self.gpu_layers.setValue(max(1, s.managed_gpu_layers))
        self.gpu_layers.setToolTip("Capas del modelo en la GPU (-ngl). 99 = todas; menos si la GPU tiene poca memoria.")
        mform.addRow("Dónde se ejecuta:", _row(self.llm_device, QLabel("capas en GPU:"), self.gpu_layers))
        self.llm_device.currentIndexChanged.connect(lambda _i: self.gpu_layers.setEnabled(self.llm_device.currentData() == "gpu"))
        self.gpu_layers.setEnabled(s.managed_device == "gpu")
        self.builtin_status = QLabel()
        self.builtin_status.setWordWrap(True)
        self.download_llm = QPushButton("Descargar…")
        self.download_llm.clicked.connect(self._download_llm)
        mform.addRow("Archivos:", _row(self.builtin_status, self.download_llm))

        self.server_path = QLineEdit(s.managed_server_path)
        self.server_path.setPlaceholderText("(el descargado)")
        browse_server = QPushButton("Examinar…")
        browse_server.clicked.connect(
            lambda: self._browse_file(self.server_path, "llama-server", "Ejecutable (*.exe);;Todos (*)")
        )
        mform.addRow("Otro llama-server:", _row(self.server_path, browse_server))
        self.gguf_path = QLineEdit(s.managed_model_path)
        self.gguf_path.setPlaceholderText("(Qwen3.5 2B descargado)")
        browse_gguf = QPushButton("Examinar…")
        browse_gguf.clicked.connect(lambda: self._browse_file(self.gguf_path, "Modelo GGUF", "GGUF (*.gguf)"))
        mform.addRow("Otro modelo .gguf:", _row(self.gguf_path, browse_gguf))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(s.managed_port)
        self.ctx = QSpinBox()
        self.ctx.setRange(1024, 131072)
        self.ctx.setSingleStep(1024)
        self.ctx.setValue(s.managed_ctx)
        mform.addRow("Puerto:", _row(self.port, QLabel("contexto (-c):"), self.ctx))
        outer.addWidget(self.managed)

        # -- externo --
        self.external = QGroupBox("Servidor externo (compatible con OpenAI)")
        form = QFormLayout(self.external)
        self.base_url = QLineEdit(s.llm_base_url)
        self.base_url.setPlaceholderText("http://localhost:8080/v1")
        self.base_url.setToolTip(
            "Cualquier servidor compatible con OpenAI, local o en otro equipo:\n"
            "llama-swap / llama-server: http://localhost:8080/v1\n"
            "Ollama: http://localhost:11434/v1\n"
            "LM Studio: http://localhost:1234/v1"
        )
        form.addRow("URL base:", self.base_url)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(260)
        if s.llm_model:
            self.model.addItem(s.llm_model)
        self.model.setCurrentText(s.llm_model)
        self.test_button = QPushButton("Probar conexión")
        self.test_button.clicked.connect(self._test_connection)
        form.addRow("Modelo:", _row(self.model, self.test_button))
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        form.addRow("", self.test_result)
        self.api_key = QLineEdit(s.llm_api_key)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("opcional")
        form.addRow("Clave API:", self.api_key)
        outer.addWidget(self.external)

        # -- comunes --
        common = QGroupBox("Corrección")
        form = QFormLayout(common)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(5, 600)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(s.llm_timeout_s)
        form.addRow("Tiempo máximo por párrafo:", self.timeout)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 1)
        self.temperature.setSingleStep(0.05)
        self.temperature.setValue(s.llm_temperature)
        form.addRow("Temperatura:", self.temperature)
        self.no_think = QCheckBox("Desactivar el razonamiento (thinking)")
        self.no_think.setChecked(s.llm_disable_thinking)
        form.addRow(self.no_think)
        self.context = QSpinBox()
        self.context.setRange(0, 5)
        self.context.setValue(s.context_paragraphs)
        form.addRow("Párrafos anteriores como contexto:", self.context)
        self.max_distance = QDoubleSpinBox()
        self.max_distance.setRange(0.02, 1)
        self.max_distance.setSingleStep(0.05)
        self.max_distance.setValue(s.guard_max_distance)
        self.max_distance.setToolTip("Distancia de edición máxima (normalizada) entre el original y la corrección.")
        form.addRow("Cambio máximo permitido:", self.max_distance)
        self.max_length = QDoubleSpinBox()
        self.max_length.setRange(0.05, 1)
        self.max_length.setSingleStep(0.05)
        self.max_length.setValue(s.guard_max_length_change)
        form.addRow("Variación máxima de longitud:", self.max_length)
        outer.addWidget(common)
        outer.addStretch()

        self.source.currentIndexChanged.connect(self._update_source)
        self._update_source()
        self._update_builtin_status()
        return w

    def _update_source(self) -> None:
        builtin = bool(self.source.currentData())
        self.managed.setEnabled(builtin)
        self.external.setEnabled(not builtin)

    def _models_dir(self):
        from pathlib import Path

        return Path(self.models_dir.text().strip()) if self.models_dir.text().strip() else default_models_dir()

    def _update_builtin_status(self) -> None:
        from dictado.models.download import LLM_PACKS, pack_present

        missing = [p for p in LLM_PACKS if not pack_present(self._models_dir(), p)]
        if missing:
            size = sum(p.size for p in missing) / 1_000_000
            self.builtin_status.setText(f"Faltan por descargar ({size:,.0f} MB).".replace(",", "."))
        else:
            self.builtin_status.setText("✓ Qwen3.5 2B y llama-server instalados.")
        self.download_llm.setVisible(bool(missing))

    def _download_llm(self) -> None:
        from dictado.ui.models_dialog import ModelsDialog

        ModelsDialog(self._models_dir(), self, include_llm=True).exec()
        self._update_builtin_status()

    def _browse_file(self, edit: QLineEdit, title: str, filters: str) -> None:
        name, _ = QFileDialog.getOpenFileName(self, title, edit.text(), filters)
        if name:
            edit.setText(name)

    def _glossary_tab(self, s: Settings) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(
            QLabel(
                "Nombres propios y términos que el corrector debe escribir exactamente así, uno por línea.\n"
                "Este glosario vale para todos los documentos; cada documento tiene además el suyo "
                "(Documento › Glosario del documento)."
            )
        )
        self.glossary = QPlainTextEdit("\n".join(s.glossary))
        layout.addWidget(self.glossary)
        return w

    # -- acciones -------------------------------------------------------------------------------------------------

    def _browse_models(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta de modelos", self.models_dir.text() or str(default_models_dir()))
        if d:
            self.models_dir.setText(d)

    def _test_connection(self) -> None:
        self.test_button.setEnabled(False)
        self.test_result.setText("Conectando…")
        url, key = self.base_url.text().strip(), self.api_key.text().strip()
        probe = self._probe
        fake = self.fake_llm

        def run():
            from dictado.llm.client import FakeLLMClient, LLMClient, LLMError

            try:
                client = FakeLLMClient() if fake else LLMClient(url, "", key, timeout=10)
                models = client.list_models()
            except (LLMError, Exception) as e:  # noqa: BLE001
                probe.done.emit(None, str(e))
                return
            probe.done.emit(models, f"Conectado: {len(models)} modelo(s) disponibles.")

        threading.Thread(target=run, daemon=True).start()

    def _on_probe(self, models, message: str) -> None:
        self.test_button.setEnabled(True)
        self.test_result.setText(message if models is not None else f"✗ {message}")
        if models:
            current = self.model.currentText()
            self.model.clear()
            self.model.addItems(models)
            self.model.setCurrentText(current if current in models or current else models[0])

    def result_settings(self) -> Settings:
        glossary = [line.strip() for line in self.glossary.toPlainText().splitlines() if line.strip()]
        return replace(
            self._original,
            mode=self.mode.currentData(),
            font_size=self.font_size.value(),
            theme=self.theme.currentData(),
            autosave_s=self.autosave.value(),
            models_dir=self.models_dir.text().strip(),
            input_device=self.device.currentData() or "",
            short_pause_ms=self.short_pause.value(),
            long_pause_ms=max(self.long_pause.value(), self.short_pause.value() + 200),
            poetry_verse_pause_ms=self.verse_pause.value(),
            poetry_stanza_pause_ms=max(self.stanza_pause.value(), self.verse_pause.value() + 200),
            live_text=self.live_text.isChecked(),
            save_session_audio=self.save_audio.isChecked(),
            vad_threshold=round(self.vad_threshold.value(), 2),
            voice_commands=self.voice_commands.isChecked(),
            llm_base_url=self.base_url.text().strip(),
            llm_model=self.model.currentText().strip(),
            llm_api_key=self.api_key.text().strip(),
            llm_timeout_s=self.timeout.value(),
            llm_temperature=round(self.temperature.value(), 2),
            llm_disable_thinking=self.no_think.isChecked(),
            context_paragraphs=self.context.value(),
            guard_max_distance=round(self.max_distance.value(), 2),
            guard_max_length_change=round(self.max_length.value(), 2),
            glossary=glossary,
            managed_enabled=bool(self.source.currentData()),
            managed_device=self.llm_device.currentData(),
            managed_server_path=self.server_path.text().strip(),
            managed_model_path=self.gguf_path.text().strip(),
            managed_gpu_layers=self.gpu_layers.value(),
            managed_port=self.port.value(),
            managed_ctx=self.ctx.value(),
        )
