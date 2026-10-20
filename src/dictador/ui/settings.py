"""Ajustes: pocas opciones, grandes y explicadas; lo técnico queda plegado en «Opciones avanzadas»."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dictador.config import Settings, default_models_dir
from dictador.ui import style
from dictador.ui.theme import THEME_LABELS, THEMES
from dictador.ui.widgets import Badge, Combo, SegmentedControl, Switch

FONT_SIZES = (12, 14, 16, 18, 20, 22, 24, 28, 32, 36)
PARAGRAPH_PAUSES = [("1800", "Corta", "Unos 2 segundos de silencio"), ("2500", "Normal", "Unos 2,5 segundos"),
                    ("4000", "Larga", "Unos 4 segundos")]


def _closest(value: int, options: list[tuple[str, str, str]]) -> str:
    return min(options, key=lambda o: abs(int(o[0]) - value))[0]


class _Stepper(QWidget):
    """«−  18  +»: más fácil de usar que una casilla con flechitas."""

    def __init__(self, value: int, values: tuple[int, ...]):
        super().__init__()
        self._values = sorted(set(values) | {value})
        self._value = value
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.minus = QPushButton("−")
        self.plus = QPushButton("+")
        self.label = QLabel()
        self.label.setFont(style.ui_font(16, QFont.Weight.DemiBold))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumWidth(52)
        for b, step in ((self.minus, -1), (self.plus, +1)):
            b.setProperty("stepper", True)
            b.setFixedWidth(56)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, step=step: self._step(step))
        row.addWidget(self.minus)
        row.addWidget(self.label)
        row.addWidget(self.plus)
        self._show()

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:  # noqa: N802 (como los de Qt)
        if value not in self._values:
            self._values = sorted(set(self._values) | {value})
        self._value = value
        self._show()

    def _step(self, step: int) -> None:
        i = max(0, min(len(self._values) - 1, self._values.index(self._value) + step))
        self.setValue(self._values[i])

    def _show(self) -> None:
        self.label.setText(str(self._value))
        self.minus.setEnabled(self._value != self._values[0])
        self.plus.setEnabled(self._value != self._values[-1])


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None, fake_llm: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.resize(780, 820)
        self._original = settings
        self.fake_llm = fake_llm
        s = settings

        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(36, 28, 36, 20)
        self.body.setSpacing(18)
        title = QLabel("Ajustes")
        title.setFont(style.display_font(24))
        self.body.addWidget(title)

        self._appearance(s)
        self._dictation(s)
        self._corrector(s)
        self._advanced(s)
        self._update_builtin_status()  # depende de la carpeta de modelos, que está en las avanzadas
        self.body.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Guardar los cambios")
        save.setProperty("primary", True)
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(36, 12, 36, 22)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

    # -- piezas ---------------------------------------------------------------------------------------------------

    def _card(self, icon: str, title: str, color: str = "ACCENT") -> QVBoxLayout:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(Badge(icon, color, 44))
        label = QLabel(title)
        label.setFont(style.display_font(17))
        head.addWidget(label, 1)
        layout.addLayout(head)
        self.body.addWidget(card)
        return layout

    @staticmethod
    def _option(layout: QVBoxLayout, text: str, help_text: str, control: QWidget, below: bool = False) -> None:
        """Una opción: el nombre (y una explicación corta) a la izquierda y el control a la derecha o debajo."""
        texts = QVBoxLayout()
        texts.setSpacing(2)
        label = QLabel(text)
        label.setFont(style.ui_font(14))
        label.setWordWrap(True)
        texts.addWidget(label)
        if help_text:
            hint = QLabel(help_text)
            hint.setFont(style.ui_font(11.5))
            hint.setProperty("soft", True)
            hint.setWordWrap(True)
            texts.addWidget(hint)
        if below:
            layout.addLayout(texts)
            layout.addWidget(control)
            return
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addLayout(texts, 1)
        row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(row)

    # -- secciones ------------------------------------------------------------------------------------------------

    def _appearance(self, s: Settings) -> None:
        card = self._card(style.ICON_THEME, "Aspecto")
        self.theme = SegmentedControl([(k, THEME_LABELS[k], "") for k in THEMES])
        self.theme.set_current(s.theme if s.theme in THEMES else "claro", animate=False)
        self._option(card, "Colores", "Claro como el papel, u oscuro para descansar la vista.", self.theme)
        self.font_size = _Stepper(s.font_size, FONT_SIZES)
        self._option(card, "Tamaño de la letra", "También con los botones «Letra −» y «Letra +».", self.font_size)
        self.italic = Switch(s.document_italic)
        self._option(card, "Texto en cursiva", "Como el que aparece mientras habla.", self.italic)

    def _dictation(self, s: Settings) -> None:
        card = self._card(style.ICON_MIC, "Micrófono y dictado")
        self.device = Combo()
        self.device.addItem("El micrófono de siempre (predeterminado)", "")
        try:
            from dictador.audio.capture import list_input_devices

            for name in list_input_devices():
                self.device.addItem(name, name)
        except Exception:  # noqa: BLE001
            pass
        self.device.setCurrentIndex(max(0, self.device.findData(s.input_device)))
        self._option(card, "Micrófono", "", self.device, below=True)
        self._pause_start = _closest(s.long_pause_ms, PARAGRAPH_PAUSES)
        self.paragraph_pause = SegmentedControl(PARAGRAPH_PAUSES)
        self.paragraph_pause.set_current(self._pause_start, animate=False)
        self._option(card, "Silencio para empezar un párrafo",
                     "Si a veces se le corta el párrafo mientras piensa, elija «Larga».", self.paragraph_pause)
        self.live_text = Switch(s.live_text)
        self._option(card, "Ver lo que digo mientras hablo", "Aparece en gris y se completa al hacer una pausa.",
                     self.live_text)
        self.voice_commands = Switch(s.voice_commands)
        self._option(card, "Entender órdenes de voz",
                     "«punto y aparte», «borra la última frase», «título: …»", self.voice_commands)

    def _corrector(self, s: Settings) -> None:
        card = self._card(style.ICON_CHECK, "Corrector", "SUCCESS")
        self.builtin_status = QLabel()
        self.builtin_status.setFont(style.ui_font(13))
        self.builtin_status.setWordWrap(True)
        self.download_llm = QPushButton("Descargar")
        self.download_llm.setProperty("small", True)
        self.download_llm.clicked.connect(self._download_llm)
        row = QHBoxLayout()
        row.addWidget(self.builtin_status, 1)
        row.addWidget(self.download_llm)
        card.addLayout(row)
        options = [("cpu", "Procesador", ""), ("gpu", "Tarjeta gráfica", "")]
        self._external = bool(s.llm_model) and not s.managed_enabled
        if self._external:
            options.append(("externo", "Servidor externo", "El que está configurado en config.json"))
        self.where = SegmentedControl(options)
        self._where_start = "externo" if self._external else s.managed_device
        self.where.set_current(self._where_start, animate=False)
        self._option(card, "Dónde trabaja",
                     "La tarjeta gráfica es más rápida, pero no funciona bien en todos los equipos.", self.where)

    def _advanced(self, s: Settings) -> None:
        self.more = QPushButton("Mostrar las opciones avanzadas")
        self.more.setProperty("link", True)
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.clicked.connect(self._toggle_advanced)
        self.body.addWidget(self.more, 0, Qt.AlignmentFlag.AlignLeft)

        self.advanced = QFrame()
        self.advanced.setObjectName("card")
        form = QFormLayout(self.advanced)
        form.setContentsMargins(24, 20, 24, 20)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        def label(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setFont(style.ui_font(12.5))
            return lab

        def spin(low, high, step, value, suffix="", double=False):
            box = QDoubleSpinBox() if double else QSpinBox()
            box.setRange(low, high)
            box.setSingleStep(step)
            box.setValue(value)
            box.setSuffix(suffix)
            box.setMinimumWidth(150)
            return box

        self.autosave = spin(10, 3600, 10, s.autosave_s, " s")
        form.addRow(label("Copia de seguridad cada"), self.autosave)
        self.vad_threshold = spin(0.1, 0.95, 0.05, s.vad_threshold, double=True)
        self.vad_threshold.setToolTip("Más alto: hace falta una voz más clara para empezar a escribir (menos ruido).")
        form.addRow(label("Exigencia del micrófono (0,1–0,95)"), self.vad_threshold)
        self.short_pause = spin(300, 3000, 100, s.short_pause_ms, " ms")
        form.addRow(label("Pausa que cierra la frase"), self.short_pause)
        self.verse_pause = spin(150, 2000, 50, s.poetry_verse_pause_ms, " ms")
        form.addRow(label("Poesía: pausa que cierra el verso"), self.verse_pause)
        self.stanza_pause = spin(500, 10000, 100, s.poetry_stanza_pause_ms, " ms")
        form.addRow(label("Poesía: pausa que cierra la estrofa"), self.stanza_pause)
        self.gpu_layers = spin(1, 999, 1, max(1, s.managed_gpu_layers))
        self.gpu_layers.setToolTip("Capas del modelo en la tarjeta gráfica (-ngl). 99 = todas.")
        form.addRow(label("Capas en la tarjeta gráfica"), self.gpu_layers)
        self.models_dir = QLineEdit(s.models_dir)
        self.models_dir.setPlaceholderText(str(default_models_dir()))
        self.models_dir.editingFinished.connect(self._update_builtin_status)
        browse = QPushButton("Examinar…")
        browse.setProperty("small", True)
        browse.clicked.connect(self._browse_models)
        folder = QHBoxLayout()
        folder.addWidget(self.models_dir, 1)
        folder.addWidget(browse)
        form.addRow(label("Carpeta de los modelos"), folder)
        self.save_audio = Switch(s.save_session_audio)
        self.save_audio.setToolTip("En %LOCALAPPDATA%\\Dictador\\diagnostico")
        form.addRow(label("Guardar el audio para diagnóstico"), self.save_audio)
        self.glossary = QPlainTextEdit("\n".join(s.glossary))
        self.glossary.setPlaceholderText("Un nombre por línea")
        self.glossary.setFixedHeight(120)
        form.addRow(label("Nombres para todos\nlos documentos"), self.glossary)
        self.advanced.hide()
        self.body.addWidget(self.advanced)

    # -- acciones -------------------------------------------------------------------------------------------------

    def _toggle_advanced(self) -> None:
        show = self.advanced.isHidden()
        self.advanced.setVisible(show)
        self.more.setText("Ocultar las opciones avanzadas" if show else "Mostrar las opciones avanzadas")

    def _models_dir(self) -> Path:
        text = self.models_dir.text().strip()
        return Path(text) if text else default_models_dir()

    def _update_builtin_status(self) -> None:
        from dictador.models.download import LLM_PACKS, pack_present

        missing = [p for p in LLM_PACKS if not pack_present(self._models_dir(), p)]
        if missing:
            size = f"{sum(p.size for p in missing) / 1_000_000:,.0f}".replace(",", ".")
            self.builtin_status.setText(f"Corrige las faltas y la puntuación. Falta descargarlo ({size} MB).")
        else:
            self.builtin_status.setText("✓  Instalado. Corrige las faltas y la puntuación en este equipo.")
        self.builtin_status.setProperty("ok", not missing)
        self.builtin_status.style().unpolish(self.builtin_status)
        self.builtin_status.style().polish(self.builtin_status)
        self.download_llm.setVisible(bool(missing))

    def _download_llm(self) -> None:
        from dictador.ui.models_dialog import ModelsDialog

        ModelsDialog(self._models_dir(), self, include_llm=True).exec()
        self._update_builtin_status()

    def _browse_models(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta de los modelos", str(self._models_dir()))
        if d:
            self.models_dir.setText(d)
            self._update_builtin_status()

    def result_settings(self) -> Settings:
        s = self._original
        glossary = [line.strip() for line in self.glossary.toPlainText().splitlines() if line.strip()]
        pause = self.paragraph_pause.current()
        long_pause = s.long_pause_ms if pause == self._pause_start else int(pause)
        where = self.where.current()
        return replace(
            s,
            theme=self.theme.current(),
            font_size=self.font_size.value(),
            document_italic=self.italic.isChecked(),
            input_device=self.device.currentData() or "",
            long_pause_ms=max(long_pause, self.short_pause.value() + 200),
            live_text=self.live_text.isChecked(),
            voice_commands=self.voice_commands.isChecked(),
            managed_enabled=s.managed_enabled if where == self._where_start else where != "externo",
            managed_device=where if where != "externo" else s.managed_device,
            autosave_s=self.autosave.value(),
            vad_threshold=round(self.vad_threshold.value(), 2),
            short_pause_ms=self.short_pause.value(),
            poetry_verse_pause_ms=self.verse_pause.value(),
            poetry_stanza_pause_ms=max(self.stanza_pause.value(), self.verse_pause.value() + 200),
            managed_gpu_layers=self.gpu_layers.value(),
            models_dir=self.models_dir.text().strip(),
            save_session_audio=self.save_audio.isChecked(),
            glossary=glossary,
        )
