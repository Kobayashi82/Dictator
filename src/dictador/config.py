"""Ajustes persistentes (JSON en %APPDATA%\\Dictador)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_NAME = "Dictador"
_OLD_NAME = "Dictado"  # nombre de las primeras versiones


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / APP_NAME


def localdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share"
    return Path(base) / APP_NAME


def default_models_dir() -> Path:
    return localdata_dir() / "models"


def recovery_dir() -> Path:
    return localdata_dir() / "recovery"


def migrate_old_folders() -> None:
    """Las carpetas de datos de cuando el programa se llamaba «Dictado» pasan a «Dictador» (así no hay que volver a
    descargar los modelos ni se pierden los ajustes)."""
    for new in (appdata_dir(), localdata_dir()):
        old = new.with_name(_OLD_NAME)
        if old.is_dir() and not new.exists():
            try:
                old.rename(new)
            except OSError:
                pass


MODES = ("prosa", "poesia", "notas", "ninguno")


@dataclass
class Settings:
    # General
    mode: str = "prosa"
    models_dir: str = ""
    input_device: str = ""  # nombre del micrófono; vacío = predeterminado
    autosave_s: int = 60
    font_size: int = 18
    theme: str = "claro"  # claro | oscuro | sistema
    language: str = ""  # es | en: interfaz y dictado; vacío = el de Windows
    document_italic: bool = True  # el texto en cursiva, como lo que aparece mientras se habla
    onboarding_done: bool = False  # el asistente de la primera vez ya se completó
    voice_commands: bool = True
    dictate_key: str = "F9"  # tecla para empezar y parar de hablar (mantenida, para al soltarla)
    recent_files: list[str] = field(default_factory=list)

    # Segmentación
    short_pause_ms: int = 800
    long_pause_ms: int = 2500
    poetry_verse_pause_ms: int = 350
    poetry_stanza_pause_ms: int = 1300
    vad_threshold: float = 0.5
    max_sentence_s: float = 20.0
    live_text: bool = True  # mostrar lo que se dice mientras se habla
    save_session_audio: bool = False  # diagnóstico

    # LLM
    llm_base_url: str = "http://localhost:8080/v1"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_s: float = 60.0
    llm_temperature: float = 0.1
    llm_disable_thinking: bool = True
    context_paragraphs: int = 2
    guard_max_distance: float = 0.2
    guard_max_length_change: float = 0.25
    guard_max_removed: float = 0.35  # en prosa: lo que puede quitar al limpiar titubeos
    glossary: list[str] = field(default_factory=list)
    # «idioma/modo» («es/prosa», «en/poesia») → instrucciones propias del corrector (si no, las de serie)
    custom_prompts: dict[str, str] = field(default_factory=dict)
    highlight_changes: bool = False  # mostrar marcas y cambios del corrector (vista avanzada)

    # Corrector integrado (llama-server propio; rutas vacías = lo descargado en la carpeta de modelos)
    managed_enabled: bool = False
    managed_device: str = "cpu"  # cpu | gpu
    managed_server_path: str = ""
    managed_model_path: str = ""
    managed_gpu_layers: int = 99
    managed_port: int = 8089
    managed_ctx: int = 4096

    def models_path(self) -> Path:
        return Path(self.models_dir) if self.models_dir else default_models_dir()

    @classmethod
    def path(cls) -> Path:
        return appdata_dir() / "config.json"

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or cls.path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in data.items() if k in known})
        old = str(localdata_dir().with_name(_OLD_NAME))
        if settings.models_dir.startswith(old):
            settings.models_dir = str(localdata_dir()) + settings.models_dir[len(old) :]
        if settings.mode not in MODES:
            settings.mode = "prosa"
        if not isinstance(settings.custom_prompts, dict):
            settings.custom_prompts = {}
        # Las primeras versiones guardaban solo el modo: eran instrucciones en español.
        settings.custom_prompts = {(k if "/" in k else f"es/{k}"): v for k, v in settings.custom_prompts.items()}
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def add_recent(self, file: str, limit: int = 8) -> None:
        file = str(Path(file))
        self.recent_files = [file] + [f for f in self.recent_files if f != file][: limit - 1]
