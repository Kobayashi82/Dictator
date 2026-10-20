"""Silero VAD en streaming y segmentación por pausas (frase / párrafo)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
FRAME = 512  # muestras por trama de Silero a 16 kHz (32 ms)
FRAME_MS = FRAME * 1000 / SAMPLE_RATE
_CONTEXT = 64  # muestras de la trama anterior que Silero espera delante de cada trama


class SileroVad:
    """Probabilidad de voz por trama de 512 muestras, con estado entre llamadas.

    Usa el `silero_vad.onnx` que descarga onnx-asr (entradas `input`, `state`, `sr`; salidas `output`, `stateN`).
    """

    def __init__(self, model_dir: Path):
        import onnxruntime as rt

        model = Path(model_dir) / "silero_vad.onnx"
        if not model.is_file():
            raise FileNotFoundError(model)
        opts = rt.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self._session = rt.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])
        self._sr = np.array([SAMPLE_RATE], dtype=np.int64)
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(_CONTEXT, dtype=np.float32)

    def __call__(self, frame: np.ndarray) -> float:
        x = np.concatenate([self._context, frame.astype(np.float32, copy=False)])[None, :]
        out, self._state = self._session.run(["output", "stateN"], {"input": x, "state": self._state, "sr": self._sr})
        self._context = frame[-_CONTEXT:].astype(np.float32, copy=True)
        return float(out[0, 0])


@dataclass
class Sentence:
    audio: np.ndarray
    forced: bool = False  # cortada por llegar a la duración máxima, no por una pausa


@dataclass
class ParagraphBreak:
    pass


Event = Sentence | ParagraphBreak


class Segmenter:
    """Convierte tramas + probabilidad de voz en frases (pausa corta) y saltos de párrafo (pausa larga).

    No sabe nada de Silero: recibe la probabilidad ya calculada, así se puede probar con valores sintéticos.
    """

    def __init__(
        self,
        short_pause_ms: float = 800,
        long_pause_ms: float = 2500,
        threshold: float = 0.5,
        min_speech_ms: float = 200,
        max_sentence_s: float = 20,
        pre_roll_ms: float = 200,
        tail_ms: float = 150,
    ):
        self.threshold = threshold
        self.neg_threshold = max(0.0, threshold - 0.15)
        self.short_frames = max(1, round(short_pause_ms / FRAME_MS))
        self.long_frames = max(self.short_frames + 1, round(long_pause_ms / FRAME_MS))
        self.min_speech_frames = max(1, round(min_speech_ms / FRAME_MS))
        self.max_frames = max(2, round(max_sentence_s * 1000 / FRAME_MS))
        self.tail_frames = round(tail_ms / FRAME_MS)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=max(0, round(pre_roll_ms / FRAME_MS)))
        self._frames: list[np.ndarray] = []
        self._in_speech = False
        self._speech_frames = 0
        self._silence = 0  # tramas seguidas sin voz
        self._sentence_open = False  # hay frases en el párrafo desde el último salto
        self.speaking = False

    def feed(self, frame: np.ndarray, prob: float) -> list[Event]:
        events: list[Event] = []
        voiced = prob >= self.threshold if not self._in_speech else prob >= self.neg_threshold
        self.speaking = self._in_speech

        if not self._in_speech:
            if voiced:
                self._in_speech = True
                self._frames = list(self._pre_roll) + [frame]
                self._pre_roll.clear()
                self._speech_frames = 1
                self._silence = 0
            else:
                self._pre_roll.append(frame)
                self._silence += 1
                if self._sentence_open and self._silence >= self.long_frames:
                    self._sentence_open = False
                    events.append(ParagraphBreak())
            self.speaking = self._in_speech
            return events

        self._frames.append(frame)
        if voiced:
            self._speech_frames += 1
            self._silence = 0
        else:
            self._silence += 1

        if self._silence >= self.short_frames:
            events.extend(self._emit(trim=self._silence))
        elif len(self._frames) >= self.max_frames:
            events.extend(self._emit(trim=0, forced=True))
            # Seguimos dentro de la voz: la siguiente frase empieza ya.
            self._in_speech = True
            self._speech_frames = 0
        self.speaking = self._in_speech
        return events

    def _emit(self, trim: int, forced: bool = False) -> list[Event]:
        frames = self._frames
        keep = len(frames) - max(0, trim - self.tail_frames)
        frames = frames[:keep]
        speech = self._speech_frames
        silence = self._silence
        self._frames = []
        self._in_speech = False
        self._speech_frames = 0
        if speech < self.min_speech_frames or not frames:
            # Un ruido corto: no es una frase. Si había un párrafo abierto, la pausa sigue contando.
            self._silence = silence
            return []
        self._sentence_open = True
        self._silence = silence
        return [Sentence(np.concatenate(frames), forced=forced)]

    def flush(self) -> list[Event]:
        """Cierra la frase en curso (al pausar el dictado o al pedir un párrafo nuevo)."""
        if self._in_speech and self._frames:
            events = self._emit(trim=self._silence)
        else:
            events = []
        self._pre_roll.clear()
        self.speaking = False
        return events

    def mark_paragraph_closed(self) -> None:
        """El párrafo se cerró por otra vía (botón, comando de voz): no volver a emitir el salto."""
        self._sentence_open = False
