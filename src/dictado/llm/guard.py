"""Salvaguarda: limpia la salida del LLM y rechaza correcciones que se pasan de la raya."""

from __future__ import annotations

import re
from dataclasses import dataclass

_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"^.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", re.DOTALL)
_TAG_WRAP = re.compile(r"^<([a-zA-Z_]+)>\s*(.*?)\s*</\1>$", re.DOTALL)
_PREAMBLE = re.compile(
    r"^\s*(?:¡?claro[!,.]?\s*|por supuesto[,.]?\s*|vale[,.]?\s*)?"
    r"(?:aqu[ií] (?:tienes|est[aá])|este es|a continuaci[oó]n|te dejo|texto corregido|versi[oó]n corregida|"
    r"correcci[oó]n|here is|corrected text)[^\n:]*:\s*\n*",
    re.IGNORECASE,
)
_LABEL = re.compile(r"^\s*(?:texto(?: corregido)?|resultado|salida|output)\s*:\s*", re.IGNORECASE)
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
    r"d[eé]cim[oa]|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|y|luego|despu[eé]s|por [uú]ltimo)\b",
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


def validate(
    raw: str,
    output: str,
    mode: str,
    max_distance: float = 0.2,
    max_length_change: float = 0.25,
) -> GuardResult:
    """Devuelve la corrección limpia si es aceptable o el motivo del rechazo."""
    text = clean_output(output, raw)
    if not text:
        return GuardResult(False, "", "El corrector no devolvió texto.")

    if mode == "poesia":
        raw_lines = [line for line in raw.strip().split("\n") if line.strip()]
        out_lines = [line for line in text.split("\n") if line.strip()]
        if len(raw_lines) != len(out_lines):
            return GuardResult(False, text, f"Cambia el número de versos ({len(raw_lines)} → {len(out_lines)}).")
        text = "\n".join(line.strip() for line in out_lines)

    a = _normalize(raw.strip(), mode)
    b = _normalize(text, mode)
    longest = max(len(a), len(b), 1)

    # En textos cortos unos pocos signos ya son mucho porcentaje: se permite un margen absoluto.
    length_diff = abs(len(b) - len(a))
    if length_diff > 8 and length_diff / max(len(a), 1) > max_length_change:
        return GuardResult(False, text, f"La longitud cambia un {length_diff / max(len(a), 1):.0%}.")

    distance = levenshtein(a, b)
    if distance > 6 and distance / longest > max_distance:
        return GuardResult(False, text, f"Cambia demasiado el texto ({distance / longest:.0%} de diferencia).")

    return GuardResult(True, text)
