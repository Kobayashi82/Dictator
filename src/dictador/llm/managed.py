"""Modo gestionado: Dictador arranca su propio llama-server (build CPU o Vulkan) y lo para al salir."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


def free_port(preferred: int) -> int:
    """El puerto pedido si está libre; si no (p. ej. un llama-server de otra sesión), otro que dé el sistema."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise OSError("No hay ningún puerto libre para el corrector.")


_job = None  # trabajo de Windows al que pertenecen los llama-server: muere con este proceso


def _tie_to_this_process(proc: subprocess.Popen) -> None:
    """Windows: si Dictador se cierra de golpe o se cuelga, el sistema cierra también su llama-server (si no,
    se queda ocupando memoria y el puerto)."""
    global _job
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    if _job is None:
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return  # 9 = JobObjectExtendedLimitInformation
        _job = job
    kernel32.AssignProcessToJobObject(_job, int(proc._handle))


class ManagedServer:
    def __init__(self, exe: str, model: str, port: int, gpu_layers: int, ctx: int, log_path: Path):
        self.exe = exe
        self.model = model
        self.requested_port = port
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
        mine = (self.exe, self.model, self.requested_port, self.gpu_layers, self.ctx)
        return mine == (exe, model, port, gpu_layers, ctx)

    def start(self) -> None:
        if not Path(self.exe).is_file():
            raise FileNotFoundError(f"No se encuentra llama-server: {self.exe}")
        if not Path(self.model).is_file():
            raise FileNotFoundError(f"No se encuentra el modelo: {self.model}")
        self.port = free_port(self.requested_port)
        args = [
            self.exe,
            "-m", self.model,
            "--alias", self.model_name,  # sin esto el servidor se presenta con la ruta del archivo
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
        try:
            _tie_to_this_process(self._proc)
        except Exception:  # noqa: BLE001
            pass  # sin esto funciona igual; solo se pierde la limpieza si el programa se cierra mal
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
