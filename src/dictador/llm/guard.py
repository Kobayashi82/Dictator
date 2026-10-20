"""Salvaguarda: limpia la salida del LLM y rechaza correcciones que se pasan de la raya."""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

from dictador.i18n import tr

_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"^.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", re.DOTALL)
_TAG_WRAP = re.compile(r"^<([a-zA-Z_]+)>\s*(.*?)\s*</\1>$", re.DOTALL)
_PREAMBLE = re.compile(
    r"^\s*(?:¡?claro[!,.]?\s*|por supuesto[,.]?\s*|vale[,.]?\s*|sure[!,.]?\s*|of course[!,.]?\s*|okay[!,.]?\s*)?"
    r"(?:aqu[ií] (?:tienes|est[aá])|este es|a continuaci[oó]n|te dejo|texto corregido|versi[oó]n corregida|"
    r"correcci[oó]n|here is|here's|this is the|below is|corrected text|corrected version)[^\n:]*:\s*\n*",
    re.IGNORECASE,
)
_LABEL = re.compile(
    r"^\s*(?:texto(?: corregido)?|resultado|salida|output|(?:corrected )?text|result)\s*:\s*", re.IGNORECASE
)
_QUOTES = [("«", "»"), ('"', '"'), ("“", "”"), ("'", "'"), ("‘", "’")]
_LIST_MARK = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)


@dataclass
class GuardResult:
    ok: bool
    text: str
    reason: str = ""


def clean_output(text: str, raw: str) -> str:
    """Quita lo que un modelo pequeño suele añadir alrededor de la respuesta."""
    text = _THINK.sub("", text)
    if "</think>" in text.lower():
        text = _UNCLOSED_THINK.sub("", text)
    text = text.strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1).strip()
    text = _PREAMBLE.sub("", text, count=1).strip()
    text = _LABEL.sub("", text, count=1).strip()
    m = _TAG_WRAP.match(text)
    if m:
        text = m.group(2).strip()
    raw_s = raw.strip()
    for left, right in _QUOTES:
        if (
            len(text) >= 2
            and text.startswith(left)
            and text.endswith(right)
            and not (raw_s.startswith(left) and raw_s.endswith(right))
            and text.count(left) + (0 if left == right else text.count(right)) <= 2
        ):
            text = text[len(left) : -len(right)].strip()
            break
    return text


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


_ORDINALS = re.compile(
    r"\b(?:primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]|"
    r"d[eé]cim[oa]|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|y|luego|despu[eé]s|por [uú]ltimo|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|one|two|three|four|five|six|seven|eight|"
    r"nine|ten|and|then|after that|finally|lastly)\b",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^\w\s]")


def _normalize(text: str, mode: str) -> str:
    if mode == "notas":
        # Lo que la lista sustituye (marcas, numeración hablada, puntuación) no cuenta como cambio.
        text = _LIST_MARK.sub("", text)
        text = _PUNCT.sub(" ", text).lower()
        text = _ORDINALS.sub(" ", text)
    if mode != "poesia":
        text = " ".join(text.split())
    return text


_WORD = re.compile(r"\w+")


def _fold_words(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return _WORD.findall(text)


def _similar(a: str, b: str) -> bool:
    """La misma palabra mal transcrita («esperava» / «esperaba», «asombra» / «asomaban»)."""
    longest = max(len(a), len(b))
    return longest > 0 and 1 - levenshtein(a, b) / longest >= 0.6


def word_changes(raw: str, text: str) -> tuple[int, int, int]:
    """(palabras nuevas, palabras quitadas, palabras del original), sin contar tildes, mayúsculas ni puntuación.

    Una palabra cambiada por otra parecida (una errata de transcripción) no cuenta como nueva ni como quitada.
    """
    a, b = _fold_words(raw), _fold_words(text)
    added = removed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "delete":
            removed += i2 - i1
        elif tag == "insert":
            added += j2 - j1
        elif tag == "replace":
            similar = sum(_similar(x, y) for x, y in zip(a[i1:i2], b[j1:j2]))
            added += (j2 - j1) - similar
            removed += (i2 - i1) - similar
    return added, removed, len(a)


def validate(
    raw: str,
    output: str,
    mode: str,
    max_distance: float = 0.2,
    max_length_change: float = 0.25,
    max_removed: float = 0.35,
) -> GuardResult:
    """Devuelve la corrección limpia si es aceptable o el motivo del rechazo."""
    text = clean_output(output, raw)
    if not text:
        return GuardResult(False, "", tr("El corrector no devolvió texto."))

    if mode == "poesia":
        raw_lines = [line for line in raw.strip().split("\n") if line.strip()]
        out_lines = [line for line in text.split("\n") if line.strip()]
        if len(raw_lines) != len(out_lines):
            return GuardResult(False, text, tr("Cambia el número de versos ({before} → {after}).", before=len(raw_lines), after=len(out_lines)))
        text = "\n".join(line.strip() for line in out_lines)

    if mode == "prosa":
        return _validate_prose(raw, text, max_distance, max_length_change, max_removed)

    a = _normalize(raw.strip(), mode)
    b = _normalize(text, mode)
    longest = max(len(a), len(b), 1)

    # En textos cortos unos pocos signos ya son mucho porcentaje: se permite un margen absoluto.
    length_diff = abs(len(b) - len(a))
    if length_diff > 8 and length_diff / max(len(a), 1) > max_length_change:
        return GuardResult(False, text, tr("La longitud cambia un {pct}.", pct=f"{length_diff / max(len(a), 1):.0%}"))

    distance = levenshtein(a, b)
    if distance > 6 and distance / longest > max_distance:
        return GuardResult(False, text, tr("Cambia demasiado el texto ({pct} de diferencia).", pct=f"{distance / longest:.0%}"))

    return GuardResult(True, text)


def _validate_prose(raw: str, text: str, max_new: float, max_growth: float, max_removed: float) -> GuardResult:
    """En prosa el corrector puede quitar titubeos (repeticiones, autocorrecciones, muletillas), así que se mide
    por separado lo que añade o cambia, con poco margen, y lo que quita, con más."""
    added, removed, total = word_changes(raw, text)
    total = max(total, 1)
    # Unas pocas palabras siempre se permiten: en un texto corto ya son mucho porcentaje.
    if added > 2 and added / total > max_new:
        return GuardResult(False, text, tr("Añade o cambia demasiadas palabras ({count} de {total}).", count=added, total=total))
    if removed > 3 and removed / total > max_removed:
        return GuardResult(False, text, tr("Quita demasiado texto ({count} de {total} palabras).", count=removed, total=total))
    growth = len(text) - len(raw.strip())
    if growth > 8 and growth / max(len(raw.strip()), 1) > max_growth:
        return GuardResult(False, text, tr("La longitud crece un {pct}.", pct=f"{growth / max(len(raw.strip()), 1):.0%}"))
    return GuardResult(True, text)
