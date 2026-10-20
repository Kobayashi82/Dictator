"""Asistente de descarga de modelos (primer arranque y Herramientas › Modelos)."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from dictador.i18n import tr
from dictador.models.download import (
    LLM_PACKS,
    VOICE_PACKS,
    DownloadCancelled,
    ModelPack,
    download_packs,
    pack_present,
)


CANCELLED = "cancelada"  # lo que devuelve el hilo de descarga si se cancela


def _mb(n: int) -> str:
    return f"{n / 1_000_000:,.0f} MB".replace(",", ".")


class _Worker(QObject):
    progress = Signal(object, object, str)  # hecho, total (int grandes: object), texto
    finished = Signal(str)  # vacío si todo bien; si no, el error


class ModelsDialog(QDialog):
    def __init__(self, models_dir: Path, parent=None, first_run: bool = False, include_llm: bool = False):
        super().__init__(parent)
        self.models_dir = Path(models_dir)
        self.setWindowTitle(tr("Bienvenida a Dictador") if first_run else tr("Modelos"))
        self.setMinimumWidth(520)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

        layout = QVBoxLayout(self)
        intro = (
            tr("Para dictar hacen falta dos modelos que funcionan en su equipo, sin conexión. "
               "Se descargan una sola vez desde Hugging Face y se verifica su integridad.")
            if first_run
            else tr("Modelos instalados en:")
        )
        label = QLabel(intro)
        label.setWordWrap(True)
        layout.addWidget(label)
        path = QLabel(f"<small>{self.models_dir}</small>")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path)

        self._checks: list[tuple[QCheckBox, ModelPack]] = []
        for pack in (*VOICE_PACKS, *LLM_PACKS):
            present = pack_present(self.models_dir, pack)
            text = tr("{title} — {size} · licencia {license}", title=pack.title, size=_mb(pack.size), license=pack.license)
            if present:
                text += tr("  ✓ instalado")
            box = QCheckBox(text)
            box.setChecked(not present and (pack not in LLM_PACKS or include_llm))
            box.setEnabled(not present)
            layout.addWidget(box)
            self._checks.append((box, pack))
        note = QLabel(
            "<small>" + tr("Los dos últimos son el corrector: corrige las faltas y la puntuación en este equipo, "
                           "sin conexión.") + "</small>"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.status = QLabel("")
        layout.addWidget(self.bar)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.download_button = QPushButton(tr("Descargar"))
        self.download_button.setDefault(True)
        self.download_button.clicked.connect(self.start)
        self.close_button = QPushButton(tr("Más tarde") if first_run else tr("Cerrar"))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self._worker = _Worker(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._refresh_button()
        for box, _ in self._checks:
            box.toggled.connect(self._refresh_button)

    def _selected(self) -> list[ModelPack]:
        return [pack for box, pack in self._checks if box.isChecked() and box.isEnabled()]

    def _refresh_button(self) -> None:
        packs = self._selected()
        self.download_button.setEnabled(bool(packs) and self._thread is None)
        self.download_button.setText(tr("Descargar ({size})", size=_mb(sum(p.size for p in packs))) if packs
                                     else tr("Descargar"))

    def start(self) -> None:
        packs = self._selected()
        if not packs:
            return
        self._cancel.clear()
        for box, _ in self._checks:
            box.setEnabled(False)
        self.download_button.setEnabled(False)
        self.close_button.setText(tr("Cancelar"))
        worker, cancel, folder = self._worker, self._cancel, self.models_dir

        def run():
            try:
                download_packs(packs, folder, lambda d, t, s: worker.progress.emit(d, t, s), cancel)
            except DownloadCancelled:
                worker.finished.emit(CANCELLED)
            except Exception as e:  # noqa: BLE001
                worker.finished.emit(tr("No se pudo descargar: {error}", error=e))
            else:
                worker.finished.emit("")

        self._thread = threading.Thread(target=run, daemon=True, name="descarga")
        self._thread.start()

    def _on_progress(self, done, total, text: str) -> None:
        self.bar.setValue(int(done * 1000 / max(total, 1)))
        self.status.setText(tr("{what} — {done} de {total}", what=text, done=_mb(done), total=_mb(total)))

    def _on_finished(self, error: str) -> None:
        self._thread = None
        self.close_button.setText(tr("Cerrar"))
        if error:
            self.status.setText(tr("Descarga cancelada.") if error == CANCELLED else error)
            for box, pack in self._checks:
                box.setEnabled(not pack_present(self.models_dir, pack))
            self._refresh_button()
            if error != CANCELLED:
                QMessageBox.warning(self, tr("Modelos"), error)
            return
        self.bar.setValue(1000)
        self.status.setText(tr("Modelos listos."))
        self.accept()

    def reject(self) -> None:
        if self._thread is not None:
            self._cancel.set()  # el hilo termina y llama a _on_finished
            self.status.setText(tr("Cancelando…"))
            return
        super().reject()
