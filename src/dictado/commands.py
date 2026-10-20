"""Comandos de voz: se detectan con reglas en cada frase transcrita, antes de que llegue al documento.

La comparación es por sonido (clave fonética española, como en K-Desktop) para tolerar los deslices de Parakeet:
«punto y a parte», «nuevo parágrafo», «borra la última frace»…
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from dictado.llm.guard import levenshtein


@dataclass
class Text:
    text: str


@dataclass
class NewParagraph:
    pass


@dataclass
class DeleteLastSentence:
    pass


@dataclass
class Title:
    text: str


Action = Text | NewParagraph | DeleteLastSentence | Title

PARAGRAPH_PHRASES = ("punto y aparte", "nuevo parrafo", "nueva estrofa")
DELETE_PHRASES = ("borra la ultima frase", "borrar la ultima frase", "borra ultima frase", "borra la frase anterior")
TITLE_WORDS = ("titulo",)
THRESHOLD = 0.85


def fold(text: str) -> str:
    """Minúsculas, sin tildes ni signos, espacios simples."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9ñ]+", " ", text)
    return " ".join(text.split())


def phonetic_key(text: str) -> str:
    """Clave «suena como» en español: c/k/qu → k, z/ce/ci → s, v/w → b, h muda, ll → y, ge/gi → j, x → ks…"""
    s = fold(text).replace(" ", "").replace("ñ", "n")
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        after = s[i + 2] if i + 2 < len(s) else ""
        if c == "q":
            out.append("k")
            if nxt == "u" and after in ("e", "i"):
                i += 1
        elif c == "c":
            if nxt == "h":
                out.append("X")
                i += 1
            else:
                out.append("s" if nxt in ("e", "i") else "k")
        elif c == "z":
            out.append("s")
        elif c in ("v", "w"):
            out.append("b")
        elif c == "h":
            pass
        elif c == "l" and nxt == "l":
            out.append("y")
            i += 1
        elif c == "y":
            out.append("y" if nxt in "aeiou" and nxt else "i")
        elif c == "g":
            if nxt in ("e", "i") and nxt:
                out.append("j")
            else:
                out.append("g")
                if nxt == "u" and after in ("e", "i"):
                    i += 1
        elif c == "x":
            out.append("ks")
        elif c == "p" and nxt == "h":
            out.append("f")
            i += 1
        else:
            out.append(c)
        i += 1
    key = []
    for ch in "".join(out):
        if not key or key[-1] != ch:
            key.append(ch)
    return "".join(key)


def similarity(a: str, b: str) -> float:
    longest = max(len(a), len(b))
    return 1.0 if longest == 0 else 1 - levenshtein(a, b) / longest


def _sounds_like(said: str, phrases: tuple[str, ...]) -> bool:
    key = phonetic_key(said)
    return any(similarity(key, phonetic_key(p)) >= THRESHOLD for p in phrases)


def _words(text: str) -> list[re.Match]:
    return list(re.finditer(r"\S+", text))


def parse(sentence: str) -> list[Action]:
    """Convierte una frase en acciones. Lo que no es un comando sale tal cual como `Text`."""
    sentence = sentence.strip()
    folded = fold(sentence)
    if not folded:
        return [Text(sentence)] if sentence else []

    if _sounds_like(folded, PARAGRAPH_PHRASES):
        return [NewParagraph()]
    if _sounds_like(folded, DELETE_PHRASES):
        return [DeleteLastSentence()]

    words = _words(sentence)
    first = fold(words[0].group(0))
    # Para el título, la palabra exacta: «títulos», «titular»… son texto normal.
    if first in TITLE_WORDS and len(words) > 1:
        rest = sentence[words[1].start() :].strip(" ,.:;")
        if rest:
            return [Title(rest[0].upper() + rest[1:])]

    # «…y se fue. Punto y aparte.»: el comando al final de una frase más larga.
    for phrase in PARAGRAPH_PHRASES:
        n = len(phrase.split())
        if len(words) > n:
            tail = " ".join(w.group(0) for w in words[-n:])
            if _sounds_like(tail, (phrase,)):
                before = sentence[: words[-n].start()].rstrip(" ,;:")
                return [Text(before), NewParagraph()] if fold(before) else [NewParagraph()]

    return [Text(sentence)]
