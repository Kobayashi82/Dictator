"""Transcripción con Parakeet TDT 0.6B v3 (onnx-asr, CPU)."""

from __future__ import annotations

import itertools
import time
from pathlib import Path

import numpy as np

from dictado.audio.vad import SAMPLE_RATE

MODEL_NAME = "nemo-parakeet-tdt-0.6b-v3"
MODEL_DIR = "parakeet-tdt-0.6b-v3"
QUANTIZATION = "int8"


class ParakeetASR:
    def __init__(self, models_dir: Path):
        import onnx_asr

        path = Path(models_dir) / MODEL_DIR
        if not path.is_dir():
            raise FileNotFoundError(path)
        self._model = onnx_asr.load_model(
            MODEL_NAME, path, quantization=QUANTIZATION, providers=["CPUExecutionProvider"]
        )
        # Un poco de silencio detrás ayuda a que salga la última palabra.
        self._tail = np.zeros(SAMPLE_RATE // 3, dtype=np.float32)

    def transcribe(self, audio: np.ndarray) -> str:
        audio = np.concatenate([audio.astype(np.float32, copy=False), self._tail])
        return str(self._model.recognize(audio, sample_rate=SAMPLE_RATE)).strip()


_FAKE_SENTENCES = [
    "Era una mañana tranquila en el pueblo.",
    "Los vecinos salian a la calle con las primeras luces.",
    "Nadie esperava la carta que llegó ese dia.",
    "El cartero, un hombre mayor, la dejó en la puerta de la iglesia.",
    "Punto y aparte.",
    "Dentro había un mapa y una sola palabra escrita a mano.",
    "La palabra era volver.",
    "Durante semanas nadie se atrevio a abrir el sobre de nuevo.",
]


class FakeASR:
    """Para probar la interfaz sin modelos: devuelve frases de ejemplo con una latencia simulada."""

    def __init__(self, *_args, latency: float = 0.3):
        self._cycle = itertools.cycle(_FAKE_SENTENCES)
        self._next = next(self._cycle)
        self.latency = latency

    def peek(self) -> str:
        """La frase que saldrá a continuación (para simular el texto en vivo)."""
        return self._next

    def transcribe(self, audio: np.ndarray | None = None) -> str:
        time.sleep(self.latency)
        text, self._next = self._next, next(self._cycle)
        return text
