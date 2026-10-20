"""Arranque: `uv run dictado [archivo.dictado] [--fake-asr] [--fake-llm]`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dictado", description="Dictado por voz a un documento, en local.")
    parser.add_argument("archivo", nargs="?", help="proyecto .dictado que abrir")
    parser.add_argument("--fake-asr", action="store_true", help="frases de ejemplo en lugar del micrófono y Parakeet")
    parser.add_argument("--fake-llm", action="store_true", help="corrector simulado en lugar del LLM")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from dictado.config import APP_NAME, Settings
    from dictado.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    settings = Settings.load()
    window = MainWindow(settings, fake_asr=args.fake_asr, fake_llm=args.fake_llm)
    window.show()
    window.offer_recovery()
    if args.archivo:
        window.open_path(Path(args.archivo))
    if not args.fake_asr:
        from dictado.engine import models_present

        if models_present(settings.models_path()):
            window.engine.preload()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
