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
    """Hace de micrófono con un .wav. `speed`: veces el tiempo real (None = todo lo rápido que se pueda)."""

    file = "dictado_es.wav"
    speed: float | None = None

    def __init__(self, _device=""):
        with wave.open(str(DATA / self.file)) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        audio = np.concatenate([audio, np.zeros(16000 * 4, dtype=np.float32)])
        self.frames = [audio[i : i + FRAME] for i in range(0, len(audio) - FRAME + 1, FRAME)]
        self.t0 = time.monotonic()
        self.sent = 0

    def start(self):
        pass

    def stop(self):
        pass

    def read(self, timeout=0.2):
        if not self.frames:
            time.sleep(0.01)
            return []
        if self.speed is None:
            n = 50
        else:
            time.sleep(0.02)
            due = int((time.monotonic() - self.t0) * self.speed * 16000 / FRAME)
            n = max(0, due - self.sent)
        out, self.frames = self.frames[:n], self.frames[n:]
        self.sent += len(out)
        return out


def run_until_done(app, window, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        statuses = [p.status for p in window.model.paragraphs]
        if statuses and "dictating" not in statuses and window.engine._pending == 0 and not window.capture_left():
            break
        time.sleep(0.02)
    window.engine.shutdown()
    app.processEvents()


def test_dictation_end_to_end(monkeypatch, tmp_path):
    import dictado.audio.capture as capture

    monkeypatch.setattr(capture, "AudioCapture", WavCapture)
    app = QApplication.instance() or QApplication([])
    from dictado.ui.main_window import MainWindow

    settings = Settings(models_dir=str(MODELS), mode="ninguno")
    window = MainWindow(settings)
    captures = []
    monkeypatch.setattr(capture, "AudioCapture", lambda d="": captures.append(WavCapture(d)) or captures[-1])
    window.capture_left = lambda: not captures or bool(captures[-1].frames)
    window.toggle_dictation()
    run_until_done(app, window)
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


def test_poetry_live_text_verses_and_stanzas(monkeypatch):
    """Poema con 0,45 s entre versos y 1,6 s entre estrofas, leído a 2× tiempo real."""
    import dictado.audio.capture as capture

    class Poem(WavCapture):
        file = "poema_es.wav"
        speed = 2.0

    captures = []
    monkeypatch.setattr(capture, "AudioCapture", lambda d="": captures.append(Poem(d)) or captures[-1])
    app = QApplication.instance() or QApplication([])
    from dictado.ui.main_window import MainWindow

    window = MainWindow(Settings(models_dir=str(MODELS), mode="poesia", llm_model=""))
    partials = []
    window.engine.partial.connect(lambda t: t and partials.append(t))
    window.capture_left = lambda: not captures or bool(captures[-1].frames)
    window.toggle_dictation()
    run_until_done(app, window)

    stanzas = [p.text.split("\n") for p in window.model.paragraphs]
    assert len(stanzas) == 2, stanzas
    assert [len(s) for s in stanzas] == [4, 4], stanzas
    assert stanzas[0][0].startswith("Verde que te quiero verde")
    assert stanzas[1][3].lower().startswith("con ojos de fría plata")
    assert partials, "no se mostró texto en vivo"
    assert any(len(t.split()) >= 2 for t in partials)
    window.model.set_modified(False)
    window.close()
