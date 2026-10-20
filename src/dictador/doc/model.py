"""Modelo de documento: lista de párrafos con su texto crudo, corregido y estado."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field

from PySide6.QtCore import QObject, Signal

STATUSES = ("dictating", "closed", "pending", "correcting", "corrected", "rejected", "edited")
"""dictating: recibiendo frases · closed: cerrado sin corrección (modo «ninguno», títulos) · pending: en cola ·
correcting: en el LLM · corrected: corrección aceptada · rejected: corrección descartada · edited: tocado a mano."""

STYLES = ("normal", "title")

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class Paragraph:
    raw: str = ""
    corrected: str | None = None
    status: str = "dictating"
    mode: str = "prosa"
    user_edited: bool = False
    style: str = "normal"
    reason: str = ""  # por qué se rechazó la corrección (o el error)
    show_raw: bool = False  # el usuario ha revertido al original
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def text(self) -> str:
        """Lo que se ve en el editor."""
        if self.corrected is not None and not self.show_raw and (self.user_edited or self.status == "corrected"):
            return self.corrected
        return self.raw

    @property
    def joiner(self) -> str:
        return "\n" if self.mode == "poesia" else " "

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Paragraph:
        p = cls(
            raw=str(data.get("raw", "")),
            corrected=data.get("corrected"),
            status=data.get("status", "closed"),
            mode=data.get("mode", "prosa"),
            user_edited=bool(data.get("user_edited", False)),
            style=data.get("style", "normal"),
            reason=data.get("reason", ""),
            show_raw=bool(data.get("show_raw", False)),
        )
        if data.get("id"):
            p.id = str(data["id"])
        if p.status not in STATUSES:
            p.status = "closed"
        # Lo que estaba en cola o corrigiéndose al guardar vuelve a estar pendiente.
        if p.status == "correcting":
            p.status = "pending"
        return p


class DocumentModel(QObject):
    """Fuente de verdad del documento. El editor es una vista que lo refleja y le comunica las ediciones."""

    reset = Signal()
    paragraph_added = Signal(int, str)  # índice, id
    paragraph_changed = Signal(str)
    paragraph_removed = Signal(str)
    paragraph_closed = Signal(str)  # listo para corregir
    modified_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.paragraphs: list[Paragraph] = []
        self.glossary: list[str] = []
        self.mode = "prosa"
        self._modified = False

    # -- estado ---------------------------------------------------------------------------------------------------

    @property
    def modified(self) -> bool:
        return self._modified

    def set_modified(self, value: bool) -> None:
        if value != self._modified:
            self._modified = value
            self.modified_changed.emit(value)

    def get(self, pid: str) -> Paragraph | None:
        for p in self.paragraphs:
            if p.id == pid:
                return p
        return None

    def index_of(self, pid: str) -> int:
        for i, p in enumerate(self.paragraphs):
            if p.id == pid:
                return i
        return -1

    def current(self) -> Paragraph | None:
        """El párrafo que está recibiendo dictado, si lo hay (siempre el último)."""
        if self.paragraphs and self.paragraphs[-1].status == "dictating":
            return self.paragraphs[-1]
        return None

    def context_before(self, pid: str, count: int) -> list[str]:
        i = self.index_of(pid)
        if i <= 0 or count <= 0:
            return []
        return [p.text for p in self.paragraphs[max(0, i - count) : i] if p.text.strip()]

    # -- carga ----------------------------------------------------------------------------------------------------

    def load(self, paragraphs: list[Paragraph], mode: str = "prosa", glossary: list[str] | None = None) -> None:
        self.paragraphs = list(paragraphs)
        self.mode = mode
        self.glossary = list(glossary or [])
        self.reset.emit()
        self.set_modified(False)

    def clear(self) -> None:
        self.load([])

    # -- dictado --------------------------------------------------------------------------------------------------

    def append_sentence(self, text: str, mode: str) -> Paragraph:
        """Añade una frase al párrafo en dictado (o crea uno nuevo al final)."""
        text = text.strip()
        p = self.current()
        last = self.paragraphs[-1] if self.paragraphs else None
        if p is None and last is not None and last.user_edited and not last.text.strip():
            # Una línea vacía que dejó el usuario (Intro al final): se dicta en ella.
            last.raw, last.corrected, last.user_edited, last.status, last.mode = text, None, False, "dictating", mode
            self.paragraph_changed.emit(last.id)
            self.set_modified(True)
            return last
        if p is None:
            p = Paragraph(raw=text, status="dictating", mode=mode)
            self.paragraphs.append(p)
            self.paragraph_added.emit(len(self.paragraphs) - 1, p.id)
        else:
            p.raw = f"{p.raw}{p.joiner}{text}" if p.raw else text
            if p.corrected is not None:  # editado a mano mientras se dictaba
                p.corrected = f"{p.corrected}{p.joiner}{text}" if p.corrected else text
            self.paragraph_changed.emit(p.id)
        self.set_modified(True)
        return p

    def close_paragraph(self, correct: bool) -> Paragraph | None:
        """Cierra el párrafo en dictado. Si `correct`, queda pendiente de pasar por el LLM."""
        p = self.current()
        if p is None:
            return None
        if not p.text.strip():
            self.remove(p.id)
            return None
        if p.user_edited:
            p.status = "edited"
        else:
            p.status = "pending" if correct and p.mode != "ninguno" else "closed"
        self.paragraph_changed.emit(p.id)
        self.set_modified(True)
        if p.status == "pending":
            self.paragraph_closed.emit(p.id)
        return p

    def add_title(self, text: str) -> Paragraph:
        self.close_paragraph(correct=True)
        p = Paragraph(raw=text.strip(), status="closed", mode=self.mode, style="title")
        self.paragraphs.append(p)
        self.paragraph_added.emit(len(self.paragraphs) - 1, p.id)
        self.set_modified(True)
        return p

    def delete_last_sentence(self) -> bool:
        """Quita la última frase dictada: del párrafo en curso o, si está vacío, del último cerrado sin corregir."""
        p = self.current()
        if p is None:
            p = next((q for q in reversed(self.paragraphs) if q.status in ("closed", "pending", "rejected")), None)
            if p is None or p is not self.paragraphs[-1]:
                return False
        parts = p.raw.split("\n") if p.mode == "poesia" else _SENTENCE_END.split(p.raw)
        parts = [s for s in parts if s.strip()]
        if not parts:
            return False
        p.raw = p.joiner.join(parts[:-1])
        p.corrected = None if not p.user_edited else p.raw
        if not p.raw:
            self.remove(p.id)
        else:
            if p.status in ("pending", "rejected"):
                p.status = "closed"
            self.paragraph_changed.emit(p.id)
        self.set_modified(True)
        return True

    # -- corrección -----------------------------------------------------------------------------------------------

    def set_status(self, pid: str, status: str, reason: str = "") -> None:
        p = self.get(pid)
        if p is None:
            return
        p.status = status
        p.reason = reason
        self.paragraph_changed.emit(pid)

    def apply_correction(self, pid: str, raw_snapshot: str, corrected: str | None, reason: str = "") -> bool:
        """Aplica el resultado del LLM si el párrafo sigue igual que cuando se envió."""
        p = self.get(pid)
        if p is None or p.user_edited or p.raw != raw_snapshot or p.status != "correcting":
            return False
        if corrected is None:
            p.status = "rejected"
            p.reason = reason
        else:
            p.corrected = corrected
            p.status = "corrected"
            p.show_raw = False
            p.reason = ""
        self.paragraph_changed.emit(pid)
        self.set_modified(True)
        return corrected is not None

    def revert(self, pid: str) -> None:
        p = self.get(pid)
        if p and p.corrected is not None and p.status == "corrected":
            p.show_raw = not p.show_raw
            self.paragraph_changed.emit(pid)
            self.set_modified(True)

    def request_recorrect(self, pid: str) -> bool:
        p = self.get(pid)
        if p is None or p.status in ("dictating", "correcting", "pending") or p.style == "title":
            return False
        if p.user_edited:
            # Volver a corregir un párrafo editado: el texto editado pasa a ser el original.
            p.raw = p.text
            p.user_edited = False
        p.corrected = None
        p.show_raw = False
        p.status = "pending"
        p.reason = ""
        self.paragraph_changed.emit(pid)
        self.paragraph_closed.emit(pid)
        self.set_modified(True)
        return True

    # -- ediciones del usuario ------------------------------------------------------------------------------------

    def user_edit(self, pid: str, text: str) -> None:
        """El usuario cambió el texto del párrafo a mano: el LLM ya no lo toca."""
        p = self.get(pid)
        if p is None or p.text == text:
            return
        p.user_edited = True
        p.corrected = text
        p.show_raw = False
        if p.status != "dictating":
            p.status = "edited"
        self.set_modified(True)

    def user_insert(self, index: int, text: str) -> Paragraph:
        p = Paragraph(raw=text, corrected=text, status="edited", mode=self.mode, user_edited=True)
        self.paragraphs.insert(index, p)
        self.set_modified(True)
        return p

    def user_reorder(self, order: list[str]) -> None:
        """Deja los párrafos en el orden de los bloques del editor (los ausentes se borran)."""
        by_id = {p.id: p for p in self.paragraphs}
        self.paragraphs = [by_id[i] for i in order if i in by_id]
        self.set_modified(True)
        # Un párrafo en dictado que ya no es el último se cierra (el usuario escribió detrás).
        for p in self.paragraphs[:-1]:
            if p.status == "dictating":
                p.status = "edited" if p.user_edited else ("closed" if p.mode == "ninguno" else "pending")
                self.paragraph_changed.emit(p.id)
                if p.status == "pending":
                    self.paragraph_closed.emit(p.id)

    def remove(self, pid: str) -> None:
        i = self.index_of(pid)
        if i >= 0:
            del self.paragraphs[i]
            self.paragraph_removed.emit(pid)
            self.set_modified(True)

    # -- texto visible --------------------------------------------------------------------------------------------

    def visible_paragraphs(self) -> list[Paragraph]:
        return [p for p in self.paragraphs if p.text.strip()]
