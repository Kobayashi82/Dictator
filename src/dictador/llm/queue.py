"""Cola de corrección: FIFO, un párrafo cada vez, en un hilo aparte."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from dictador.llm import guard
from dictador.llm.client import LLMError
from dictador.llm.prompts import build_messages, max_tokens_for


@dataclass
class CorrectionJob:
    pid: str
    raw: str
    mode: str
    context: list[str] = field(default_factory=list)
    glossary: list[str] = field(default_factory=list)
    max_distance: float = 0.2
    max_length_change: float = 0.25
    max_removed: float = 0.35


class CorrectionQueue(QObject):
    started = Signal(str)  # id
    finished = Signal(str, str, object, str)  # id, raw enviado, corregido | None, motivo
    status = Signal(str, str)  # estado (ok | corrigiendo | error | sin-configurar), detalle

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._client = None
        self._lock = threading.Lock()
        self._queue: queue.Queue[CorrectionJob | None] = queue.Queue()
        self._queued: set[str] = set()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="corrector")
        self._thread.start()

    def set_client(self, client) -> None:
        with self._lock:
            self._client = client
        if client is None:
            self.status.emit("sin-configurar", "")
        else:
            self.check_connection()

    @property
    def configured(self) -> bool:
        return self._client is not None

    def check_connection(self) -> None:
        client = self._client

        def run():
            if client is None:
                return
            if not self._wait_ready(client):
                return
            try:
                models = client.list_models()
            except LLMError as e:
                self.status.emit("error", str(e))
                return
            if client.model not in models and models:
                self.status.emit("error", f"El servidor no tiene el modelo «{client.model}».")
            else:
                self.status.emit("ok", client.model)

        threading.Thread(target=run, daemon=True, name="llm-check").start()

    def _wait_ready(self, client) -> bool:
        """Con el servidor gestionado, espera a que cargue el modelo. False si no llegó a arrancar."""
        waiter = getattr(client, "wait_until_ready", None)
        if waiter is None:
            return True
        if not getattr(client, "is_ready", lambda: True)():
            self.status.emit("arrancando", "")
        error = waiter()
        if error:
            self.status.emit("error", error)
            return False
        return True

    def enqueue(self, job: CorrectionJob) -> None:
        with self._lock:
            if job.pid in self._queued:
                return
            self._queued.add(job.pid)
        self._queue.put(job)

    def pending(self) -> int:
        with self._lock:
            return len(self._queued)

    def shutdown(self) -> None:
        self._queue.put(None)

    def _loop(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            with self._lock:
                client = self._client
            if client is None:
                with self._lock:
                    self._queued.discard(job.pid)
                self.finished.emit(job.pid, job.raw, None, "El corrector no está configurado.")
                continue
            if not self._wait_ready(client):
                with self._lock:
                    self._queued.discard(job.pid)
                self.finished.emit(job.pid, job.raw, None, "El servidor del corrector no arrancó.")
                continue
            self.started.emit(job.pid)
            self.status.emit("corrigiendo", str(self.pending()))
            corrected, reason = None, ""
            try:
                messages = build_messages(job.mode, job.raw, job.context, job.glossary)
                output = client.complete(messages, max_tokens_for(job.raw, job.mode))
                result = guard.validate(
                    job.raw, output, job.mode, job.max_distance, job.max_length_change, job.max_removed
                )
                if result.ok:
                    corrected = result.text
                else:
                    reason = result.reason
                ok = True
            except LLMError as e:
                reason = f"Error del corrector: {e}"
                ok = False
            except Exception as e:  # noqa: BLE001
                reason = f"Error inesperado: {e}"
                ok = False
            with self._lock:
                self._queued.discard(job.pid)
            self.finished.emit(job.pid, job.raw, corrected, reason)
            if ok:
                self.status.emit("ok" if self.pending() == 0 else "corrigiendo", str(self.pending()))
            else:
                self.status.emit("error", reason)
