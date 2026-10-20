"""Descarga de modelos con progreso y verificación de integridad.

Cada archivo está fijado a un commit del repositorio de Hugging Face y a su hash: SHA-256 para los archivos LFS y el
SHA-1 de blob de git para los pequeños. Si el hash no coincide, el archivo se borra y la descarga falla.
"""

from __future__ import annotations

import hashlib
import os
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dictador.i18n import tr

HF = "https://huggingface.co"


@dataclass(frozen=True)
class ModelFile:
    repo: str
    revision: str
    name: str
    size: int
    sha256: str = ""  # archivos LFS
    git_sha1: str = ""  # archivos pequeños (hash de blob de git)
    direct_url: str = ""  # fuera de Hugging Face (p. ej. una release de GitHub)
    extract: bool = False  # zip que se descomprime en la carpeta del paquete y se borra

    @property
    def url(self) -> str:
        return self.direct_url or f"{HF}/{self.repo}/resolve/{self.revision}/{self.name}"


@dataclass(frozen=True)
class ModelPack:
    key: str
    title: str
    folder: str
    files: tuple[ModelFile, ...]
    license: str
    marker: str = ""  # para paquetes que se descomprimen: el archivo que demuestra que está instalado

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


_SILERO = "istupakov/silero-vad-onnx", "b3e3ee3cce4c11ceb63b1a0b229d916069c1ddf6"
_PARAKEET = "istupakov/parakeet-tdt-0.6b-v3-onnx", "8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce"
_QWEN = "unsloth/Qwen3.5-2B-GGUF", "f6d5376be1edb4d416d56da11e5397a961aca8ae"

SILERO = ModelPack(
    "silero",
    "Silero VAD (detector de voz)",
    "silero-vad",
    (
        ModelFile(*_SILERO, "silero_vad.onnx", 2327524, sha256="1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"),
        ModelFile(*_SILERO, "config.json", 30, git_sha1="b7ef67b9ec211c85993c5f6649bdeeac4b445d1e"),
    ),
    "MIT",
)

PARAKEET = ModelPack(
    "parakeet",
    "Parakeet TDT 0.6B v3 int8 (voz a texto)",
    "parakeet-tdt-0.6b-v3",
    (
        ModelFile(*_PARAKEET, "encoder-model.int8.onnx", 652183999, sha256="6139d2fa7e1b086097b277c7149725edbab89cc7c7ae64b23c741be4055aff09"),
        ModelFile(*_PARAKEET, "decoder_joint-model.int8.onnx", 18202004, sha256="eea7483ee3d1a30375daedc8ed83e3960c91b098812127a0d99d1c8977667a70"),
        ModelFile(*_PARAKEET, "vocab.txt", 93939, git_sha1="fc43e1c723e262df60b70e1919614417162d1fe2"),
        ModelFile(*_PARAKEET, "config.json", 97, git_sha1="02a773005666393de591dfd55230b778da1653d8"),
    ),
    "CC-BY-4.0 (NVIDIA)",
)

QWEN_2B = ModelPack(
    "qwen3.5-2b",
    "Qwen3.5 2B Q4_K_M (corrector integrado)",
    "llm",
    (
        ModelFile(*_QWEN, "Qwen3.5-2B-Q4_K_M.gguf", 1280835840, sha256="aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"),
    ),
    "Apache-2.0",
)

_LLAMA_TAG = "b11756"
LLAMA_CPP = ModelPack(
    "llama.cpp",
    f"llama-server {_LLAMA_TAG} (motor del corrector integrado: CPU y GPU Vulkan)",
    "llama.cpp",
    (
        ModelFile(
            "ggml-org/llama.cpp",
            _LLAMA_TAG,
            f"llama-{_LLAMA_TAG}-bin-win-vulkan-x64.zip",
            36751610,
            sha256="75ce69fdda503c3d6d3b3401f61369bd072194746ec65fbbc5fd7e749edd2914",
            direct_url=(
                f"https://github.com/ggml-org/llama.cpp/releases/download/{_LLAMA_TAG}/"
                f"llama-{_LLAMA_TAG}-bin-win-vulkan-x64.zip"
            ),
            extract=True,
        ),
    ),
    "MIT",
    marker="llama-server.exe",
)

VOICE_PACKS = (SILERO, PARAKEET)
LLM_PACKS = (QWEN_2B, LLAMA_CPP)


def builtin_server(models_dir: Path) -> Path:
    return Path(models_dir) / LLAMA_CPP.folder / LLAMA_CPP.marker


def builtin_model(models_dir: Path) -> Path:
    return Path(models_dir) / QWEN_2B.folder / QWEN_2B.files[0].name


class DownloadCancelled(Exception):
    pass


class IntegrityError(Exception):
    pass


def _hasher(f: ModelFile):
    if f.sha256:
        return hashlib.sha256()
    h = hashlib.sha1()
    h.update(f"blob {f.size}\0".encode())
    return h


def _expected(f: ModelFile) -> str:
    return f.sha256 or f.git_sha1


def verify(path: Path, f: ModelFile, cancel: threading.Event | None = None) -> bool:
    if not path.is_file() or path.stat().st_size != f.size:
        return False
    h = _hasher(f)
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            if cancel is not None and cancel.is_set():
                raise DownloadCancelled
            h.update(chunk)
    return h.hexdigest() == _expected(f)


def pack_present(models_dir: Path, pack: ModelPack) -> bool:
    """Comprobación rápida (por tamaño); la de hash se hace al descargar."""
    folder = Path(models_dir) / pack.folder
    if pack.marker:
        return (folder / pack.marker).is_file()
    return all((folder / f.name).is_file() and (folder / f.name).stat().st_size == f.size for f in pack.files)


Progress = Callable[[int, int, str], None]  # bytes hechos, bytes totales, texto


def download_packs(
    packs: tuple[ModelPack, ...] | list[ModelPack],
    models_dir: Path,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Descarga lo que falte de cada paquete. Los archivos ya presentes y correctos no se vuelven a bajar."""
    import urllib.request

    total = sum(p.size for p in packs)
    done = 0

    def report(text: str) -> None:
        if progress:
            progress(done, total, text)

    for pack in packs:
        folder = Path(models_dir) / pack.folder
        folder.mkdir(parents=True, exist_ok=True)
        if pack.marker and pack_present(models_dir, pack):
            done += pack.size
            report(f"{pack.title}: ya estaba")
            continue
        for f in pack.files:
            target = folder / f.name
            report(f"Comprobando {f.name}…")
            if verify(target, f, cancel):
                done += f.size
                report(f"{f.name}: ya estaba")
                continue
            part = target.with_name(target.name + ".part")
            h = _hasher(f)
            got = 0
            try:
                request = urllib.request.Request(f.url, headers={"User-Agent": "Dictador"})
                with urllib.request.urlopen(request, timeout=60) as r:
                    with part.open("wb") as out:
                        while chunk := r.read(1 << 20):
                            if cancel is not None and cancel.is_set():
                                raise DownloadCancelled
                            out.write(chunk)
                            h.update(chunk)
                            got += len(chunk)
                            done += len(chunk)
                            report(f"Descargando {f.name}")
            except BaseException:
                part.unlink(missing_ok=True)
                raise
            if got != f.size or h.hexdigest() != _expected(f):
                part.unlink(missing_ok=True)
                raise IntegrityError(tr("{name} no ha pasado la verificación de integridad (descarga corrupta).", name=f.name))
            os.replace(part, target)
            if f.extract:
                report(f"Descomprimiendo {f.name}…")
                with zipfile.ZipFile(target) as z:
                    z.extractall(folder)  # extractall descarta rutas absolutas y «..»
                target.unlink()
    report("Listo")
