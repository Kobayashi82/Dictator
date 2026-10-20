"""Arranque: `uv run dictado [archivo.dictado] [--fake-asr] [--fake-llm]`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dictador", description="Dictador: dictado por voz a un documento, en local.")
    parser.add_argument("archivo", nargs="?", help="documento .dictador que abrir")
    parser.add_argument("--fake-asr", action="store_true", help="frases de ejemplo en lugar del micrófono y Parakeet")
    parser.add_argument("--fake-llm", action="store_true", help="corrector simulado en lugar del LLM")
    parser.add_argument(
        "--transcribe",
        metavar="WAV",
        help="diagnóstico: segmenta y transcribe un .wav (16 kHz mono) sin abrir la ventana",
    )
    return parser.parse_args(argv)


def transcribe_file(wav: str) -> int:
    """Pasa un .wav por la VAD, la segmentación y Parakeet, como el micrófono. Sin consola, escribe un .txt al lado."""
    import time
    import wave

    import numpy as np

    from dictador.asr.parakeet import ParakeetASR
    from dictador.audio.vad import FRAME, SAMPLE_RATE, Segmenter, Sentence, SileroVad
    from dictador.config import Settings

    settings = Settings.load()
    lines = []
    try:
        with wave.open(wav) as w:
            if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise ValueError("el .wav debe ser PCM de 16 bits, mono, 16 kHz")
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        audio = np.concatenate([audio, np.zeros(SAMPLE_RATE * 4, dtype=np.float32)])
        t0 = time.perf_counter()
        asr = ParakeetASR(settings.models_path())
        vad = SileroVad(settings.models_path() / "silero-vad")
        lines.append(f"Modelos cargados en {time.perf_counter() - t0:.1f} s")
        seg = Segmenter(settings.short_pause_ms, settings.long_pause_ms, settings.vad_threshold)
        for i in range(0, len(audio) - FRAME + 1, FRAME):
            frame = audio[i : i + FRAME]
            for event in seg.feed(frame, vad(frame)):
                if isinstance(event, Sentence):
                    t = time.perf_counter()
                    text = asr.transcribe(event.audio)
                    lines.append(f"[{i / SAMPLE_RATE:6.1f} s] ({time.perf_counter() - t:.2f} s) {text}")
                else:
                    lines.append("--- párrafo ---")
        code = 0
    except Exception as e:  # noqa: BLE001
        lines.append(f"Error: {e}")
        code = 1
    report = "\n".join(lines) + "\n"
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(report)
    else:
        Path(wav).with_suffix(".txt").write_text(report, encoding="utf-8")
    return code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from dictador.config import migrate_old_folders

    migrate_old_folders()
    if args.transcribe:
        return transcribe_file(args.transcribe)

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from dictador.config import APP_NAME, Settings
    from dictador.ui import style
    from dictador.ui.main_window import MainWindow
    from dictador.ui.theme import apply_theme

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui" / "assets" / "dictador.png")))
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    translator = QTranslator(app)  # textos de Qt (botones estándar, atajos) en español
    if translator.load(QLocale("es_ES"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    app.setFont(style.ui_font(12))
    app.setStyleSheet(style.stylesheet())
    # El diseño es claro, como una hoja de Word, sea cual sea el tema de Windows.
    apply_theme("claro")

    settings = Settings.load()
    window = MainWindow(settings, fake_asr=args.fake_asr, fake_llm=args.fake_llm)
    window.show()
    window.offer_recovery()
    if args.archivo:
        window.open_path(Path(args.archivo))

    from dictador.engine import models_present

    if not settings.onboarding_done or not (args.fake_asr or models_present(settings.models_path())):
        QTimer.singleShot(250, window.run_onboarding)
    elif not args.fake_asr:
        window.engine.preload()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
