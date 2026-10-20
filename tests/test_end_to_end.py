"""Dictado completo con los modelos reales: el WAV de prueba hace de micrófono."""

import os
import time
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from dictado.audio.vad import FRAME
from dictado.config import Settings
from dictado.engine import models_present

DATA = Path(__file__).parent / "data"
MODELS = Path(os.environ.get("LOCALAPPDATA", "")) / "Dictado" / "models"

pytestmark = pytest.mark.skipif(not models_present(MODELS), reason="sin modelos de voz")


class WavCapture:
    def __init__(self, _device=""):
        with wave.open(str(DATA / "dictado_es.wav")) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        audio = np.concatenate([audio, np.zeros(16000 * 4, dtype=np.float32)])
        self.frames = [audio[i : i + FRAME] for i in range(0, len(audio) - FRAME + 1, FRAME)]

    def start(self):
        pass

    def stop(self):
        pass

    def read(self, timeout=0.2):
        if not self.frames:
            time.sleep(0.01)
            return []
        out, self.frames = self.frames[:50], self.frames[50:]
        return out


def test_dictation_end_to_end(monkeypatch, tmp_path):
    import dictado.audio.capture as capture

    monkeypatch.setattr(capture, "AudioCapture", WavCapture)
    app = QApplication.instance() or QApplication([])
    from dictado.ui.main_window import MainWindow

    settings = Settings(models_dir=str(MODELS), mode="ninguno")
    window = MainWindow(settings)
    window.toggle_dictation()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        app.processEvents()
        statuses = [p.status for p in window.model.paragraphs]
        if len(statuses) >= 2 and "dictating" not in statuses and window.engine._pending == 0:
            break
        time.sleep(0.02)
    window.engine.shutdown()
    texts = [p.text for p in window.model.paragraphs]
    assert len(texts) == 2, texts
    assert texts[0].startswith("Era una mañana tranquila")
    assert "primeras luces" in texts[0]
    assert texts[1].startswith("Nadie esperaba la carta")
    assert "aparte" not in texts[1].lower()  # el comando de voz no llega al texto

    path = tmp_path / "e2e.dictado"
    assert window._save_to(path)
    window.model.set_modified(False)
    window.close()
