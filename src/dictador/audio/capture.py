"""Captura del micrófono con sounddevice: tramas mono float32 a 16 kHz."""

from __future__ import annotations

import queue

import numpy as np

from dictador.audio.vad import FRAME, SAMPLE_RATE


def list_input_devices() -> list[str]:
    import sounddevice as sd

    names = []
    try:
        default_api = sd.query_devices(kind="input")["hostapi"]
    except Exception:
        default_api = 0
    for dev in sd.query_devices():
        # Solo los de la API por defecto (MME en Windows): el resto son el mismo micro repetido.
        if dev["max_input_channels"] > 0 and dev["hostapi"] == default_api and dev["name"] not in names:
            names.append(dev["name"])
    return names


def _find_device(name: str) -> int | None:
    import sounddevice as sd

    if not name:
        return None
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and dev["name"] == name:
            return i
    return None


class _Resampler:
    """Remuestreo lineal en streaming (solo si el micro no acepta 16 kHz)."""

    def __init__(self, rate_in: float):
        self.step = rate_in / SAMPLE_RATE
        self.pos = 0.0
        self.last = np.zeros(0, dtype=np.float32)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self.last, x])
        idx = np.arange(self.pos, len(buf) - 1, self.step)
        out = np.interp(idx, np.arange(len(buf)), buf).astype(np.float32)
        consumed = int(idx[-1]) if len(idx) else 0
        self.pos = (idx[-1] + self.step - consumed) if len(idx) else self.pos
        self.last = buf[consumed:]
        return out


class AudioCapture:
    """Abre el micro y entrega tramas de `FRAME` muestras. `read()` se llama desde un hilo de trabajo."""

    def __init__(self, device_name: str = ""):
        self.device_name = device_name
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = None
        self._pending = np.zeros(0, dtype=np.float32)
        self._resampler: _Resampler | None = None
        self.overflows = 0

    def start(self) -> None:
        import sounddevice as sd

        device = _find_device(self.device_name)
        try:
            self._open(sd, device, SAMPLE_RATE)
        except sd.PortAudioError:
            rate = sd.query_devices(device if device is not None else sd.default.device[0])["default_samplerate"]
            self._resampler = _Resampler(rate)
            self._open(sd, device, int(rate))

    def _open(self, sd, device, rate: int) -> None:
        def callback(indata, frames, time_info, status):  # hilo de audio: lo mínimo posible
            if status.input_overflow:
                self.overflows += 1
            self._queue.put(indata[:, 0].copy())

        self._stream = sd.InputStream(
            device=device, channels=1, samplerate=rate, dtype="float32", blocksize=FRAME, callback=callback
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def read(self, timeout: float = 0.2) -> list[np.ndarray]:
        """Tramas completas disponibles (espera hasta `timeout` por la primera)."""
        try:
            chunks = [self._queue.get(timeout=timeout)]
        except queue.Empty:
            return []
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        data = np.concatenate(chunks)
        if self._resampler is not None:
            data = self._resampler(data)
        data = np.concatenate([self._pending, data])
        n = len(data) // FRAME
        self._pending = data[n * FRAME :]
        return [data[i * FRAME : (i + 1) * FRAME] for i in range(n)]
