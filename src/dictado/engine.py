"""Motor de dictado: captura + VAD en un hilo, ASR en otro, resultados por señales Qt en orden."""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from dictado.audio.vad import ParagraphBreak, Segmenter, Sentence
from dictado.config import Settings

_BREAK = object()  # marcador de párrafo en la cola del ASR
_STOP = object()


class DictationEngine(QObject):
    """Las señales se emiten desde hilos de trabajo; Qt las entrega en el hilo de la UI."""

    sentence = Signal(str)
    paragraph_break = Signal()
    level = Signal(float)  # 0..1
    speaking = Signal(bool)
    state = Signal(str)  # "cargando" | "escuchando" | "parado"
    error = Signal(str)
    asr_busy = Signal(int)  # frases esperando transcripción

    def __init__(self, settings: Settings, fake_asr: bool = False, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self.fake_asr = fake_asr
        self._asr = None
        self._asr_lock = threading.Lock()
        self._asr_queue: queue.Queue = queue.Queue()
        self._asr_thread: threading.Thread | None = None
        self._capture_thread: threading.Thread | None = None
        self._running = threading.Event()
        self._break_requested = threading.Event()
        self._pending = 0
        self._pending_lock = threading.Lock()

    # -- modelo ---------------------------------------------------------------------------------------------------

    def _ensure_asr(self):
        with self._asr_lock:
            if self._asr is None:
                if self.fake_asr:
                    from dictado.asr.parakeet import FakeASR

                    self._asr = FakeASR()
                else:
                    from dictado.asr.parakeet import ParakeetASR

                    self._asr = ParakeetASR(self.settings.models_path())
            return self._asr

    def preload(self) -> None:
        """Carga Parakeet en segundo plano para que el primer dictado no espere."""

        def run():
            try:
                self._ensure_asr()
            except Exception:
                pass  # el error se mostrará al empezar a dictar

        threading.Thread(target=run, daemon=True, name="asr-preload").start()

    # -- control --------------------------------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        if self._asr_thread is None or not self._asr_thread.is_alive():
            self._asr_thread = threading.Thread(target=self._asr_loop, daemon=True, name="asr")
            self._asr_thread.start()
        target = self._fake_loop if self.fake_asr else self._capture_loop
        self._capture_thread = threading.Thread(target=target, daemon=True, name="captura")
        self._capture_thread.start()

    def stop(self) -> None:
        self._running.clear()

    def shutdown(self) -> None:
        self.stop()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2)
        self._asr_queue.put(_STOP)
        if self._asr_thread is not None:
            self._asr_thread.join(timeout=5)

    def request_paragraph_break(self) -> None:
        """Nuevo párrafo manual: se cierra la frase en curso y el salto llega detrás de ella, en orden."""
        self._break_requested.set()

    # -- hilos ----------------------------------------------------------------------------------------------------

    def _enqueue(self, item) -> None:
        if item is not _BREAK:
            self._count_pending(+1)
        self._asr_queue.put(item)

    def _count_pending(self, delta: int) -> None:
        with self._pending_lock:
            self._pending += delta
            pending = self._pending
        self.asr_busy.emit(pending)

    def _capture_loop(self) -> None:
        from dictado.audio.capture import AudioCapture
        from dictado.audio.vad import SileroVad

        self.state.emit("cargando")
        capture = None
        try:
            self._ensure_asr()
            vad = SileroVad(self.settings.models_path() / "silero-vad")
            s = self.settings
            seg = Segmenter(s.short_pause_ms, s.long_pause_ms, s.vad_threshold, max_sentence_s=s.max_sentence_s)
            capture = AudioCapture(s.input_device)
            capture.start()
        except Exception as e:  # noqa: BLE001
            self._running.clear()
            if capture is not None:
                capture.stop()
            self.error.emit(f"No se puede empezar a dictar: {e}")
            self.state.emit("parado")
            return

        self.state.emit("escuchando")
        last_level = 0.0
        was_speaking = False
        try:
            while self._running.is_set():
                frames = capture.read(timeout=0.1)
                for frame in frames:
                    for event in seg.feed(frame, vad(frame)):
                        self._enqueue(event.audio if isinstance(event, Sentence) else _BREAK)
                if frames:
                    rms = float(np.sqrt(np.mean(np.square(np.concatenate(frames)))))
                    now = time.monotonic()
                    if now - last_level > 0.05:
                        last_level = now
                        self.level.emit(min(1.0, rms * 8))
                if seg.speaking != was_speaking:
                    was_speaking = seg.speaking
                    self.speaking.emit(was_speaking)
                if self._break_requested.is_set():
                    self._break_requested.clear()
                    for event in seg.flush():
                        self._enqueue(event.audio)
                    seg.mark_paragraph_closed()
                    self._enqueue(_BREAK)
        finally:
            capture.stop()
            for event in seg.flush():
                if isinstance(event, Sentence):
                    self._enqueue(event.audio)
            self.level.emit(0.0)
            self.speaking.emit(False)
            self.state.emit("parado")

    def _fake_loop(self) -> None:
        """--fake-asr: una frase cada ~1,5 s y un salto de párrafo cada cuatro, sin micrófono ni VAD."""
        self.state.emit("escuchando")
        count = 0
        t0 = time.monotonic()
        while self._running.is_set():
            time.sleep(0.05)
            phase = (time.monotonic() - t0) % 1.5
            self.level.emit(0.5 + 0.4 * np.sin(phase * 9) if phase < 1.0 else 0.02)
            if self._break_requested.is_set():
                self._break_requested.clear()
                self._enqueue(_BREAK)
            if time.monotonic() - t0 >= 1.5 * (count + 1):
                count += 1
                self._enqueue(np.zeros(1, dtype=np.float32))
                if count % 4 == 0:
                    self._enqueue(_BREAK)
        self.level.emit(0.0)
        self.state.emit("parado")

    def _asr_loop(self) -> None:
        while True:
            item = self._asr_queue.get()
            if item is _STOP:
                return
            if item is _BREAK:
                self.paragraph_break.emit()
                continue
            try:
                text = self._ensure_asr().transcribe(item)
            except Exception as e:  # noqa: BLE001
                self.error.emit(f"Error al transcribir: {e}")
                text = ""
            finally:
                self._count_pending(-1)
            if text:
                self.sentence.emit(text)


def models_present(models_dir: Path) -> bool:
    from dictado.asr.parakeet import MODEL_DIR

    return (models_dir / "silero-vad" / "silero_vad.onnx").is_file() and any(
        (models_dir / MODEL_DIR).glob("encoder-model*.onnx")
    )
