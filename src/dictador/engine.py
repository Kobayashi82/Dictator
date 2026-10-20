"""Motor de dictado: captura + VAD en un hilo, ASR en otro, resultados por señales Qt en orden."""

from __future__ import annotations

import queue
import threading
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from dictador.audio.vad import FRAME_MS, SAMPLE_RATE, ParagraphBreak, Segmenter, Sentence
from dictador.config import Settings, localdata_dir

_BREAK = object()  # marcador de párrafo en la cola del ASR
_STOP = object()

PARTIAL_EVERY_S = 0.4  # cada cuánto se re-transcribe la frase en curso para mostrarla en vivo
PARTIAL_MIN_S = 0.35  # audio mínimo para intentar una transcripción en vivo


@dataclass
class _Partial:
    seq: int
    audio: np.ndarray


def pauses_for(settings: Settings, mode: str) -> tuple[int, int]:
    """Pausa que cierra la frase y pausa que cierra el párrafo, según el modo."""
    if mode == "poesia":
        return settings.poetry_verse_pause_ms, settings.poetry_stanza_pause_ms
    return settings.short_pause_ms, settings.long_pause_ms


class _SessionRecorder:
    """Diagnóstico: guarda el audio de la sesión y la probabilidad de voz de cada trama."""

    def __init__(self):
        folder = localdata_dir() / "diagnostico"
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder / datetime.now().strftime("sesion-%Y%m%d-%H%M%S")
        self.wav_path = stem.with_suffix(".wav")
        self._wav = wave.open(str(self.wav_path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(SAMPLE_RATE)
        self._csv = stem.with_suffix(".csv").open("w", encoding="utf-8")
        self._csv.write("segundo;probabilidad;evento\n")
        self._t = 0.0

    def frame(self, frame: np.ndarray, prob: float, events: list) -> None:
        self._wav.writeframes((np.clip(frame, -1, 1) * 32767).astype(np.int16).tobytes())
        names = ",".join("frase" if isinstance(e, Sentence) else "parrafo" for e in events)
        self._csv.write(f"{self._t:.3f};{prob:.3f};{names}\n")
        self._t += FRAME_MS / 1000

    def note(self, text: str) -> None:
        self._csv.write(f"{self._t:.3f};;{text}\n")

    def close(self) -> None:
        self._wav.close()
        self._csv.close()


class DictationEngine(QObject):
    """Las señales se emiten desde hilos de trabajo; Qt las entrega en el hilo de la UI."""

    sentence = Signal(str)
    partial = Signal(str)  # lo que se está diciendo ahora (vacío: no hay nada en curso)
    paragraph_break = Signal()
    level = Signal(float)  # 0..1
    speaking = Signal(bool)
    state = Signal(str)  # "cargando" | "escuchando" | "parado"
    error = Signal(str)
    asr_busy = Signal(int)  # frases esperando transcripción
    recording_saved = Signal(str)  # ruta del audio de diagnóstico

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
        self._seq = 0  # sube con cada frase cerrada: las transcripciones en vivo anteriores quedan obsoletas
        self._partial_busy = threading.Event()
        self._pauses = pauses_for(settings, settings.mode)

    # -- modelo ---------------------------------------------------------------------------------------------------

    def _ensure_asr(self):
        with self._asr_lock:
            if self._asr is None:
                if self.fake_asr:
                    from dictador.asr.parakeet import FakeASR

                    self._asr = FakeASR()
                else:
                    from dictador.asr.parakeet import ParakeetASR

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

    def set_mode(self, mode: str) -> None:
        """Las pausas cambian con el modo (verso/estrofa en poesía). Se aplica en caliente."""
        self._pauses = pauses_for(self.settings, mode)

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
            self._seq += 1
            self._count_pending(+1)
        self._asr_queue.put(item)

    def _count_pending(self, delta: int) -> None:
        with self._pending_lock:
            self._pending += delta
            pending = self._pending
        self.asr_busy.emit(pending)

    def _maybe_partial(self, audio: np.ndarray | None, last: float) -> float:
        """Pide una transcripción en vivo de la frase en curso si toca y el ASR está libre."""
        now = time.monotonic()
        if (
            audio is None
            or not self.settings.live_text
            or now - last < PARTIAL_EVERY_S
            or len(audio) < PARTIAL_MIN_S * SAMPLE_RATE
            or self._partial_busy.is_set()
            or self._pending
        ):
            return last
        self._partial_busy.set()
        self._asr_queue.put(_Partial(self._seq, audio))
        return now

    def _capture_loop(self) -> None:
        from dictador.audio.capture import AudioCapture
        from dictador.audio.vad import SileroVad

        self.state.emit("cargando")
        capture = None
        recorder = None
        try:
            self._ensure_asr()
            vad = SileroVad(self.settings.models_path() / "silero-vad")
            s = self.settings
            pauses = self._pauses
            seg = Segmenter(*pauses, s.vad_threshold, max_sentence_s=s.max_sentence_s)
            capture = AudioCapture(s.input_device)
            capture.start()
            if s.save_session_audio:
                recorder = _SessionRecorder()
        except Exception as e:  # noqa: BLE001
            self._running.clear()
            if capture is not None:
                capture.stop()
            self.error.emit(f"No se puede empezar a dictar: {e}")
            self.state.emit("parado")
            return

        self.state.emit("escuchando")
        last_level = 0.0
        last_partial = 0.0
        was_speaking = False
        try:
            while self._running.is_set():
                if self._pauses != pauses:
                    pauses = self._pauses
                    seg.configure(*pauses)
                frames = capture.read(timeout=0.1)
                for frame in frames:
                    prob = vad(frame)
                    events = seg.feed(frame, prob)
                    if recorder is not None:
                        recorder.frame(frame, prob, events)
                    for event in events:
                        self._enqueue(event.audio if isinstance(event, Sentence) else _BREAK)
                if frames:
                    rms = float(np.sqrt(np.mean(np.square(np.concatenate(frames)))))
                    now = time.monotonic()
                    if now - last_level > 0.05:
                        last_level = now
                        self.level.emit(min(1.0, rms * 8))
                    last_partial = self._maybe_partial(seg.current_audio(), last_partial)
                if seg.speaking != was_speaking:
                    was_speaking = seg.speaking
                    self.speaking.emit(was_speaking)
                if self._break_requested.is_set():
                    self._break_requested.clear()
                    if recorder is not None:
                        recorder.note("parrafo manual")
                    for event in seg.flush():
                        self._enqueue(event.audio)
                    seg.mark_paragraph_closed()
                    self._enqueue(_BREAK)
        finally:
            capture.stop()
            for event in seg.flush():
                if isinstance(event, Sentence):
                    self._enqueue(event.audio)
            if recorder is not None:
                recorder.close()
                self.recording_saved.emit(str(recorder.wav_path))
            self.level.emit(0.0)
            self.speaking.emit(False)
            self.state.emit("parado")

    def _fake_loop(self) -> None:
        """--fake-asr: una frase cada ~1,5 s (que aparece palabra a palabra) y un párrafo cada cuatro."""
        self.state.emit("escuchando")
        asr = self._ensure_asr()
        count = 0
        t0 = time.monotonic()
        while self._running.is_set():
            time.sleep(0.05)
            phase = (time.monotonic() - t0) % 1.5
            self.level.emit(0.5 + 0.4 * np.sin(phase * 9) if phase < 1.0 else 0.02)
            if phase < 1.0 and self.settings.live_text:
                words = asr.peek().split()
                self.partial.emit(" ".join(words[: 1 + int(phase * len(words))]))
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
            if isinstance(item, _Partial):
                try:
                    if item.seq == self._seq:
                        text = self._ensure_asr().transcribe(item.audio)
                        if item.seq == self._seq:  # sin frase cerrada mientras tanto
                            self.partial.emit(text)
                except Exception:  # noqa: BLE001
                    pass  # lo en vivo es solo una vista previa
                finally:
                    self._partial_busy.clear()
                continue
            if item is _BREAK:
                self.partial.emit("")
                self.paragraph_break.emit()
                continue
            try:
                text = self._ensure_asr().transcribe(item)
            except Exception as e:  # noqa: BLE001
                self.error.emit(f"Error al transcribir: {e}")
                text = ""
            finally:
                self._count_pending(-1)
            self.partial.emit("")
            if text:
                self.sentence.emit(text)


def models_present(models_dir: Path) -> bool:
    from dictador.models.download import VOICE_PACKS, pack_present

    return all(pack_present(models_dir, pack) for pack in VOICE_PACKS)
