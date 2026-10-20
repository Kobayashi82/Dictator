"""Asistente de la primera vez: da la bienvenida, descarga lo necesario, prueba el micrófono y explica el uso.

Letra grande, una idea por pantalla y nada técnico.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dictador.ui import style
from dictador.ui.widgets import Badge, Combo, MicButton, SoftProgress, StepDots

TEST_PHRASE = "Hoy hace un día precioso"


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(style.display_font(26))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


def _body(text: str, size: float = 16) -> QLabel:
    label = QLabel(text)
    label.setFont(style.ui_font(size))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setProperty("soft", True)
    return label


class _Page(QWidget):
    def __init__(self, icon: str, color: str, title: str, text: str, badge: int = 96):
        super().__init__()
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(56, 36, 56, 12)
        self.layout_.setSpacing(16)
        self.badge = Badge(icon, color, badge)
        self.layout_.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = _title(title)
        self.layout_.addWidget(self.title)
        self.text = _body(text)
        self.layout_.addWidget(self.text)

    def add(self, widget: QWidget, align=Qt.AlignmentFlag.AlignHCenter) -> QWidget:
        self.layout_.addWidget(widget, 0, align)
        return widget

    def finish(self) -> None:
        self.layout_.addStretch(1)

    # Ganchos para el asistente.
    def entered(self) -> None: ...

    def left(self) -> None: ...

    def can_continue(self) -> bool:
        return True


class _Downloader(QObject):
    progress = Signal(object, object, str)
    done = Signal(str)  # vacío si todo bien


class DownloadPage(_Page):
    def __init__(self, wizard: Onboarding):
        super().__init__(
            style.ICON_DOWNLOAD,
            "ACCENT",
            "Preparando todo",
            "Estamos descargando lo que el programa necesita para entender su voz y corregir el texto.\n"
            "Puede tardar unos minutos. No hace falta hacer nada.",
        )
        self.wizard = wizard
        self.bar = SoftProgress()
        self.bar.setFixedWidth(460)
        self.add(self.bar)
        self.detail = _body("", 13)
        self.add(self.detail)
        self.retry = QPushButton("Reintentar")
        self.retry.setProperty("primary", True)
        self.retry.clicked.connect(self.start)
        self.retry.hide()
        self.add(self.retry)
        self.finish()
        self._ok = False
        self._running = False
        self._worker = _Downloader(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)

    def packs(self):
        from dictador.models.download import LLM_PACKS, VOICE_PACKS

        s = self.wizard.window.settings
        external = s.llm_model and not s.managed_enabled
        return list(VOICE_PACKS) + ([] if external else list(LLM_PACKS))

    def entered(self) -> None:
        if not self._ok and not self._running:
            self.start()

    def can_continue(self) -> bool:
        return self._ok

    def start(self) -> None:
        from dictador.models.download import download_packs, pack_present

        window = self.wizard.window
        folder = window.settings.models_path()
        packs = self.packs()
        self.retry.hide()
        self.title.setText("Preparando todo")
        if window.fake_asr or all(pack_present(folder, p) for p in packs):
            self.bar.set_value(1.0)
            self._on_done("")
            return
        self._running = True
        self.detail.setText("Empezando…")
        worker = self._worker

        def run():
            try:
                download_packs(packs, folder, lambda d, t, _s: worker.progress.emit(d, t, ""))
            except Exception as e:  # noqa: BLE001
                worker.done.emit(str(e) or e.__class__.__name__)
            else:
                worker.done.emit("")

        threading.Thread(target=run, daemon=True, name="descarga").start()

    def _on_progress(self, done, total, _text: str) -> None:
        self.bar.set_value(done / max(total, 1))
        mb = lambda n: f"{n / 1_000_000:,.0f}".replace(",", ".")  # noqa: E731
        self.detail.setText(f"{mb(done)} de {mb(total)} MB")

    def _on_done(self, error: str) -> None:
        self._running = False
        if error:
            self.title.setText("No se ha podido descargar")
            self.detail.setText("Compruebe que el ordenador está conectado a internet y pulse «Reintentar».")
            self.detail.setToolTip(error)
            self.retry.show()
            self.wizard.update_buttons()
            return
        self._ok = True
        self.title.setText("¡Todo preparado!")
        self.text.setText("Ya está todo descargado. Ahora vamos a probar el micrófono.")
        self.detail.setText("")
        self.bar.set_value(1.0)
        self.wizard.models_ready()
        self.wizard.update_buttons()
        QTimer.singleShot(900, lambda: self.wizard.current() is self and self.wizard.next())


class MicTestPage(_Page):
    def __init__(self, wizard: Onboarding):
        super().__init__(
            style.ICON_MIC,
            "ACCENT",
            "Vamos a probar el micrófono",
            f"Pulse el botón y diga cualquier cosa en voz alta, por ejemplo:\n«{TEST_PHRASE}»",
        )
        self.wizard = wizard
        self.mic = MicButton(compact=True)
        self.mic.setFixedSize(self.mic.sizeHint())
        self.mic.clicked.connect(self.toggle)
        self.add(self.mic)
        self.box = QLabel("Aquí aparecerá lo que diga…")
        self.box.setObjectName("micBox")
        self.box.setFont(QFont(style.DOCUMENT_FONT, 20))
        self.box.setWordWrap(True)
        self.box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.box.setMinimumSize(560, 96)
        self.add(self.box)
        self.feedback = QLabel("")
        self.feedback.setFont(style.ui_font(15, QFont.Weight.DemiBold))
        self.feedback.setProperty("ok", True)
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.add(self.feedback)
        self.change = QPushButton("¿No le oye? Elegir otro micrófono")
        self.change.setProperty("link", True)
        self.change.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change.clicked.connect(self._show_devices)
        self.add(self.change)
        self.devices = Combo()
        self.devices.setMinimumWidth(460)
        self.devices.hide()
        self.devices.currentIndexChanged.connect(self._device_changed)
        self.add(self.devices)
        self.finish()
        self._heard = ""
        self._connected = False

    def entered(self) -> None:
        engine = self.wizard.window.engine
        self.wizard.window.suppress_dictation = True
        if not self._connected:
            engine.partial.connect(self._on_partial)
            engine.sentence.connect(self._on_sentence)
            engine.state.connect(self._on_state)
            engine.level.connect(self.mic.set_level)
            self._connected = True

    def left(self) -> None:
        engine = self.wizard.window.engine
        if engine.running:
            engine.stop()
        if self._connected:
            for signal, slot in (
                (engine.partial, self._on_partial),
                (engine.sentence, self._on_sentence),
                (engine.state, self._on_state),
                (engine.level, self.mic.set_level),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            self._connected = False
        self.wizard.window.suppress_dictation = False
        self.mic.set_state("idle")

    def toggle(self) -> None:
        engine = self.wizard.window.engine
        if engine.running:
            engine.stop()
        else:
            self.feedback.setText("")
            engine.start()
            self.mic.set_state("loading")

    def _on_state(self, state: str) -> None:
        self.mic.set_state({"cargando": "loading", "escuchando": "listening", "parado": "idle"}[state])
        if state == "escuchando" and not self._heard:
            self.box.setText("Le escucho…")

    def _on_partial(self, text: str) -> None:
        if text:
            self._show(text, live=True)

    def _on_sentence(self, text: str) -> None:
        # Solo se comprueba que el micrófono llega bien: no hace falta decir la frase de ejemplo.
        self._heard = text
        self._show(text, live=False)
        self.feedback.setText("✓  ¡Muy bien! El micrófono funciona y le oigo bien.")

    def _show(self, text: str, live: bool) -> None:
        self.box.setProperty("heard", not live)
        self.box.style().unpolish(self.box)
        self.box.style().polish(self.box)
        self.box.setText(text)

    def _show_devices(self) -> None:
        from dictador.audio.capture import list_input_devices

        self.devices.blockSignals(True)
        self.devices.clear()
        self.devices.addItem("El micrófono de siempre (predeterminado)", "")
        try:
            for name in list_input_devices():
                self.devices.addItem(name, name)
        except Exception:  # noqa: BLE001
            pass
        current = self.wizard.window.settings.input_device
        self.devices.setCurrentIndex(max(0, self.devices.findData(current)))
        self.devices.blockSignals(False)
        self.devices.show()
        self.change.hide()

    def _device_changed(self, _index: int) -> None:
        window = self.wizard.window
        window.settings.input_device = self.devices.currentData() or ""
        if window.engine.running:  # volver a abrir el micrófono con el nuevo
            window.engine.stop()
            QTimer.singleShot(400, self.toggle)


class HowToPage(_Page):
    def __init__(self, hold: bool = False):
        super().__init__(style.ICON_IDEA, "WARNING", "Así de fácil", "", badge=76)
        self.text.hide()
        steps = [
            (style.ICON_MIC, "Mantenga pulsado el botón (o la tecla F9)\nmientras habla. Al soltarlo, para." if hold
             else "Pulse «Empezar a hablar» (o la tecla F9)\ny hable con normalidad. Verá aparecer lo que dice."),
            (style.ICON_ENTER, "Para empezar un párrafo nuevo, pulse «Nuevo párrafo»,\nhaga una pausa larga o diga «punto y aparte»."),
            (style.ICON_SAVE, ("Cuando termine, pulse «Guardar»." if hold
                               else "Cuando termine, pulse «Parar» y después «Guardar».")
             + "\nLas faltas se corrigen solas."),
        ]
        for i, (icon, text) in enumerate(steps, 1):
            card = QFrame()
            card.setObjectName("card")
            row = QHBoxLayout(card)
            row.setContentsMargins(18, 14, 22, 14)
            row.setSpacing(18)
            number = QLabel(str(i))
            number.setFixedSize(40, 40)
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number.setFont(style.display_font(16))
            number.setProperty("number", True)
            row.addWidget(number)
            glyph = QLabel(icon)
            glyph.setFont(style.icon_font(20))
            glyph.setProperty("accent", True)
            row.addWidget(glyph)
            label = QLabel(text)
            label.setFont(style.ui_font(15))
            row.addWidget(label, 1)
            card.setFixedWidth(640)
            self.add(card)
        tip = _body("Si se equivoca al hablar, no pasa nada: diga la frase bien\ny el programa se queda con lo último.", 14)
        tip.setWordWrap(False)  # dos líneas fijas: con ajuste automático Qt calculaba mal el alto
        tip.setMinimumHeight(64)
        self.add(tip)
        self.finish()


class Onboarding(QDialog):
    def __init__(self, window, intro_only: bool = False):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Bienvenida a Dictador")
        self.setModal(True)
        self.setFixedSize(840, 730)

        welcome = _Page(
            style.ICON_MIC,
            "ACCENT",
            "¡Hola!",
            "Dictador escribe lo que usted dice en voz alta.\n\n"
            "Vamos a dejarlo preparado. Solo hay que hacerlo una vez\ny no tardaremos mucho.",
        )
        welcome.finish()
        done = _Page(
            style.ICON_CHECK,
            "SUCCESS",
            "¡Todo listo!",
            "Ya puede escribir con la voz.\n\n"
            "Si alguna vez quiere volver a ver esta explicación,\npulse «Más» y luego «Ayuda».",
        )
        done.finish()
        if intro_only:
            self.pages = [HowToPage(window.settings.push_to_talk), done]
        else:
            self.pages = [welcome, DownloadPage(self), MicTestPage(self), HowToPage(window.settings.push_to_talk), done]

        self.stack = QStackedWidget()
        for page in self.pages:
            self.stack.addWidget(page)

        self.dots = StepDots(len(self.pages))
        self.back = QPushButton("Atrás")
        self.back.clicked.connect(self.previous)
        self.forward = QPushButton("Siguiente")
        self.forward.setProperty("primary", True)
        self.forward.setDefault(True)
        self.forward.clicked.connect(self.next)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(28, 0, 28, 24)
        bottom.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignVCenter)
        bottom.addStretch(1)
        bottom.addWidget(self.back)
        bottom.addWidget(self.forward)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack, 1)
        layout.addLayout(bottom)

        self._index = 0
        self._anims: list = []
        self._go(0, animate=False)

    def current(self) -> _Page:
        return self.pages[self._index]

    def models_ready(self) -> None:
        window = self.window
        s = window.settings
        if not (s.llm_model and not s.managed_enabled):
            s.managed_enabled = True  # el corrector integrado, en el procesador (no toca la tarjeta gráfica)
            s.managed_device = "cpu"
        window.save_settings()
        window.configure_llm()
        if not window.fake_asr:
            window.engine.preload()

    def update_buttons(self) -> None:
        last = self._index == len(self.pages) - 1
        self.back.setVisible(0 < self._index and not last)
        self.forward.setText("Empezar a escribir" if last else ("Empezar" if self._index == 0 and len(self.pages) > 2 else "Siguiente"))
        self.forward.setEnabled(self.current().can_continue())

    def next(self) -> None:
        if self._index == len(self.pages) - 1:
            self.accept()
            return
        if self.current().can_continue():
            self._go(self._index + 1)

    def previous(self) -> None:
        if self._index > 0:
            self._go(self._index - 1, forward=False)

    def _go(self, index: int, animate: bool = True, forward: bool = True) -> None:
        if index != self._index:
            self.current().left()
        self._index = index
        page = self.pages[index]
        self.stack.setCurrentWidget(page)
        self.dots.set_step(index)
        if animate:
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
            fade = QPropertyAnimation(effect, b"opacity", self, duration=260, startValue=0.0, endValue=1.0)
            slide = QPropertyAnimation(page, b"pos", self, duration=320, easingCurve=QEasingCurve.Type.OutCubic)
            end = page.pos()
            slide.setStartValue(end + QPoint(40 if forward else -40, 0))
            slide.setEndValue(end)
            fade.finished.connect(lambda: page.setGraphicsEffect(None))
            self._anims = [fade, slide]
            fade.start()
            slide.start()
        page.entered()
        self.update_buttons()

    def accept(self) -> None:
        self.current().left()
        if len(self.pages) > 2:
            self.window.settings.onboarding_done = True
            self.window.save_settings()
        super().accept()

    def reject(self) -> None:
        self.current().left()
        super().reject()
