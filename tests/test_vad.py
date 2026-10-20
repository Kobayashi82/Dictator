import os
import wave
from pathlib import Path

import numpy as np
import pytest

from dictador.audio.vad import FRAME, FRAME_MS, ParagraphBreak, Segmenter, Sentence

DATA = Path(__file__).parent / "data"
MODELS = Path(os.environ.get("LOCALAPPDATA", "")) / "Dictador" / "models"


def run(seg: Segmenter, pattern: list[tuple[float, float]]):
    """pattern: (probabilidad, milisegundos). Devuelve los eventos con el instante (ms) en que salen."""
    events = []
    t = 0.0
    for prob, ms in pattern:
        for _ in range(round(ms / FRAME_MS)):
            frame = np.full(FRAME, prob, dtype=np.float32)
            for ev in seg.feed(frame, prob):
                events.append((t, ev))
            t += FRAME_MS
    return events


def kinds(events):
    return ["F" if isinstance(e, Sentence) else "P" for _, e in events]


def test_short_pause_closes_sentence_long_pause_closes_paragraph():
    seg = Segmenter(short_pause_ms=800, long_pause_ms=2500)
    events = run(seg, [(0.9, 1500), (0.0, 1000), (0.9, 1200), (0.0, 3000), (0.9, 800), (0.0, 1000)])
    assert kinds(events) == ["F", "F", "P", "F"]


def test_long_pause_counts_from_end_of_speech():
    seg = Segmenter(short_pause_ms=800, long_pause_ms=2500)
    events = run(seg, [(0.0, 500), (0.9, 1000), (0.0, 4000)])
    (t_sentence, _), (t_break, _) = events
    assert abs(t_sentence - (500 + 1000 + 800)) <= 2 * FRAME_MS
    assert abs(t_break - (500 + 1000 + 2500)) <= 2 * FRAME_MS


def test_no_paragraph_break_without_sentences():
    seg = Segmenter()
    assert run(seg, [(0.0, 10_000)]) == []


def test_short_noise_is_not_a_sentence():
    seg = Segmenter(min_speech_ms=200)
    assert run(seg, [(0.9, 64), (0.0, 2000)]) == []


def test_hysteresis_keeps_sentence_open():
    # Bajadas a 0,4 (por encima del umbral negativo 0,35) no cuentan como silencio.
    seg = Segmenter(short_pause_ms=800, threshold=0.5)
    events = run(seg, [(0.9, 500), (0.4, 1000), (0.9, 500), (0.0, 1000)])
    assert kinds(events) == ["F"]


def test_max_duration_forces_cut():
    seg = Segmenter(max_sentence_s=5)
    events = run(seg, [(0.9, 12_000), (0.0, 1000)])
    sentences = [e for _, e in events if isinstance(e, Sentence)]
    assert len(sentences) == 3
    assert sentences[0].forced and sentences[1].forced and not sentences[2].forced
    assert len(sentences[0].audio) <= 5 * 16000 + FRAME


def test_trailing_silence_is_trimmed_and_pre_roll_kept():
    seg = Segmenter(short_pause_ms=800, pre_roll_ms=200, tail_ms=150)
    events = run(seg, [(0.0, 1000), (0.9, 1000), (0.0, 900)])
    (_, sentence), = events
    seconds = len(sentence.audio) / 16000
    assert 1.25 <= seconds <= 1.45  # 0,2 de pre-roll + 1 s de voz + 0,15 de cola


def test_flush_and_manual_paragraph():
    seg = Segmenter()
    run(seg, [(0.9, 1000)])
    flushed = seg.flush()
    assert len(flushed) == 1 and isinstance(flushed[0], Sentence)
    seg.mark_paragraph_closed()
    assert run(seg, [(0.0, 5000)]) == []


@pytest.mark.skipif(not (MODELS / "silero-vad" / "silero_vad.onnx").exists(), reason="sin modelo Silero")
def test_real_audio_with_silero():
    from dictador.audio.vad import SileroVad

    with wave.open(str(DATA / "dictado_es.wav")) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    audio = np.concatenate([audio, np.zeros(16000 * 4, dtype=np.float32)])
    vad = SileroVad(MODELS / "silero-vad")
    seg = Segmenter(short_pause_ms=800, long_pause_ms=2500)
    out = []
    for i in range(0, len(audio) - FRAME + 1, FRAME):
        frame = audio[i : i + FRAME]
        out.extend(seg.feed(frame, vad(frame)))
    # Grabación: 2 frases, pausa de 3,2 s, 2 frases y silencio final.
    assert ["F" if isinstance(e, Sentence) else "P" for e in out] == ["F", "F", "P", "F", "F", "P"]
    assert all(isinstance(e, ParagraphBreak) or len(e.audio) > 16000 for e in out)


def test_background_noise_between_thresholds_still_closes_sentence():
    # Tras la voz, ruido a 0,4: la histéresis lo cuenta como voz, pero no puede alargar la frase para siempre.
    seg = Segmenter(short_pause_ms=800, threshold=0.5)
    events = run(seg, [(0.9, 1000), (0.4, 2000)])
    assert kinds(events) == ["F"]
    (t, sentence), = events
    assert t <= 1000 + 1700


def test_configure_changes_pauses_live():
    seg = Segmenter(short_pause_ms=800, long_pause_ms=2500)
    seg.configure(350, 1300)
    events = run(seg, [(0.9, 800), (0.0, 450), (0.9, 800), (0.0, 1500)])
    assert kinds(events) == ["F", "F", "P"]


def test_current_audio_grows_while_speaking():
    seg = Segmenter()
    assert seg.current_audio() is None
    run(seg, [(0.9, 640)])
    first = len(seg.current_audio())
    run(seg, [(0.9, 320)])
    assert len(seg.current_audio()) > first
    run(seg, [(0.0, 1000)])
    assert seg.current_audio() is None
