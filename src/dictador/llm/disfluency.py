"""Titubeos del dictado: repeticiones y autocorrecciones, detectadas por reglas.

Los modelos pequeños los arreglan mal (con «dejaban su paso a su paso» borran la segunda aparición en vez de la
primera), así que los claros se arreglan aquí antes de llamar al corrector, y los dudosos se le señalan.
Al corregirse, lo que vale es lo último que se dijo: «dejaban su paso a su paso» → «dejaban a su paso»;
«a las ocho, no, a las nueve» → «a las nueve».
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WORD = re.compile(r"\w+")
# Por idioma: muletillas que se quitan, palabras que marcan una autocorrección («a las ocho, no, a las nueve») y
# muletillas que también son palabras normales, que solo se quitan sueltas entre comas («este», «like»).
_FILLERS = {
    "es": {"eh", "em", "emm", "mmm", "este"},
    "en": {"uh", "um", "umm", "uhm", "er", "erm", "hmm", "mmm", "like"},
}
_MARKERS = {
    "es": {"no", "digo", "perdon", "mejor", "bueno", "eh", "em", "emm", "mmm", "o", "sea"},
    "en": {"no", "sorry", "i", "mean", "rather", "well", "uh", "um", "umm", "er", "or", "actually"},
}
_COMMA_FILLERS = {"es": {"este"}, "en": {"like"}}


def _fold(word: str) -> str:
    word = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in word if unicodedata.category(c) != "Mn")


def _alike(a: str, b: str) -> bool:
    """Misma palabra o la misma empezada de otra forma («asombra» / «asomaban», «corría» / «corrían»)."""
    if a == b:
        return True
    prefix = 0
    while prefix < min(len(a), len(b)) and a[prefix] == b[prefix]:
        prefix += 1
    return prefix >= 4 or (prefix >= 3 and prefix >= min(len(a), len(b)) - 1)


@dataclass(frozen=True)
class Hesitation:
    start: int
    end: int
    text: str  # el trozo tal como aparece
    fix: str  # cómo quedaría quitando lo descartado ("" = quitarlo entero)
    sure: bool  # claramente involuntario: se arregla sin preguntar al corrector


def find_hesitations(text: str, max_n: int = 4, lang: str = "es") -> list[Hesitation]:
    """Trozos que parecen una repetición, una autocorrección o una muletilla, con la versión que quedaría."""
    words = list(_WORD.finditer(text))
    folded = [_fold(w.group(0)) for w in words]
    found_all: list[Hesitation] = []
    i = 0
    while i < len(words):
        found = None
        for n in range(max_n, 0, -1):
            # «X Y X Y», «X Y a X Y» (una palabra en medio) y «se asombra, se asomaban» (formas parecidas).
            for gap in (0, 1, 2, 3):
                j = i + n + gap
                if j + n > len(words):
                    continue
                between = folded[i + n : j]
                marked = any(w in _MARKERS[lang] for w in between)
                # Hueco de una palabra solo en frases de 2+ palabras; más hueco solo si hay una marca de
                # corrección en medio («a las ocho, no, a las nueve», «sabía, eh, sabía»).
                if gap and not (gap == 1 and n >= 2) and not marked:
                    continue
                first, second = folded[i : i + n], folded[j : j + n]
                if first[0] != second[0] or not all(_alike(a, b) for a, b in zip(first, second)):
                    continue
                if n == 1 and len(first[0]) <= 2 and first[0] != "no":
                    continue  # «a a», «y y»: demasiado cortas para fiarse
                end = j + n - 1
                if marked and end + 1 < len(words):
                    end += 1  # incluir lo que corrige: «… a las nueve»
                # Con una marca en medio se descarta todo lo anterior a la repetición; sin ella, la palabra del
                # hueco ya es parte de la versión buena («su paso a su paso» → «a su paso»).
                keep_from = words[j].start() if marked else words[i + n].start()
                # Una repetición idéntica separada por coma puede ser expresiva («que no, que no», «corre, corre»).
                comma = "," in text[words[i + n - 1].end() : words[j].start()]
                sure = marked or first != second or not comma
                a, b = words[i].start(), words[end].end()
                found = Hesitation(a, b, text[a:b], text[keep_from:b].strip(" ,"), sure)
                break
            if found:
                break
        if found:
            found_all.append(found)
            while i < len(words) and words[i].start() < found.end:
                i += 1
        else:
            i += 1
    for w, f in zip(words, folded):
        inside = any(h.start <= w.start() < h.end for h in found_all)
        if not inside and f in _FILLERS[lang] and (f not in _COMMA_FILLERS[lang] or _between_commas(text, w)):
            found_all.append(Hesitation(w.start(), w.end(), w.group(0), "", sure=True))
    return sorted(found_all, key=lambda h: h.start)


def _between_commas(text: str, word: re.Match) -> bool:
    """Una muletilla suelta entre comas («un huerto, este, muy grande»); «este perro» no lo es."""
    before = text[: word.start()].rstrip()
    after = text[word.end() :].lstrip()
    return (not before or before.endswith(",")) and (not after or after[0] in ",.")


def repair(text: str, lang: str = "es") -> tuple[str, list[Hesitation]]:
    """Arregla los titubeos claros. Devuelve el texto arreglado y los dudosos, para señalárselos al corrector."""
    hesitations = find_hesitations(text, lang=lang)
    doubtful = [h for h in hesitations if not h.sure]
    out = text
    for h in sorted((h for h in hesitations if h.sure), key=lambda h: h.start, reverse=True):
        fix = h.fix
        if fix and h.text[:1].isupper():
            fix = fix[0].upper() + fix[1:]
        before, after = out[: h.start], out[h.end :]
        if not fix:
            # Quitar una muletilla con sus comas: «un huerto, este, muy grande» → «un huerto, muy grande».
            before = before.rstrip()
            after = after.lstrip()
            if after.startswith(","):
                after = after[1:].lstrip()
            sep = " " if before and after and after[0] not in ".,;:!?" else ""
            if after and (not before or before[-1] in ".!?"):
                after = after[0].upper() + after[1:]  # «Eh, empezamos» → «Empezamos»
            out = before + sep + after
            continue
        out = before + fix + after
    return out, doubtful
