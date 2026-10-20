"""Modo gestionado: Dictado arranca su propio llama-server (build CPU o Vulkan) y lo para al salir."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


class ManagedServer:
    def __init__(self, exe: str, model: str, port: int, gpu_layers: int, ctx: int, log_path: Path):
        self.exe = exe
        self.model = model
        self.port = port
        self.gpu_layers = gpu_layers
        self.ctx = ctx
        self.log_path = log_path
        self._proc: subprocess.Popen | None = None
        self.ready = threading.Event()
        self.error = ""

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def model_name(self) -> str:
        return Path(self.model).stem

    def same_config(self, exe: str, model: str, port: int, gpu_layers: int, ctx: int) -> bool:
        return (self.exe, self.model, self.port, self.gpu_layers, self.ctx) == (exe, model, port, gpu_layers, ctx)

    def start(self) -> None:
        if not Path(self.exe).is_file():
            raise FileNotFoundError(f"No se encuentra llama-server: {self.exe}")
        if not Path(self.model).is_file():
            raise FileNotFoundError(f"No se encuentra el modelo: {self.model}")
        args = [
            self.exe,
            "-m", self.model,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "-ngl", str(self.gpu_layers),
            "-c", str(self.ctx),
        ]  # fmt: skip
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open("w", encoding="utf-8", errors="replace")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        log.close()
        threading.Thread(target=self._wait_ready, daemon=True, name="llama-server").start()

    def _wait_ready(self, timeout: float = 180) -> None:
        url = f"http://127.0.0.1:{self.port}/health"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc is None or self._proc.poll() is not None:
                self.error = f"llama-server se cerró al arrancar (mira {self.log_path})."
                self.ready.set()
                return
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if r.status == 200:
                        self.ready.set()
                        return
            except OSError:
                pass  # aún cargando (503) o sin escuchar
            time.sleep(0.5)
        self.error = "llama-server no respondió a tiempo."
        self.ready.set()

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
