"""Prompts por modo de corrección."""

from __future__ import annotations

from dictador.llm.disfluency import repair

_COMMON = (
    "El texto viene de un reconocedor de voz en español. "
    "Devuelve SOLO el texto corregido: sin comillas, sin explicaciones, sin encabezados y sin repetir el contexto."
)

PRESETS = {
    "prosa": (
        "Eres un corrector de textos dictados por voz. Recibes lo que alguien ha dicho en voz alta y devuelves el "
        "texto tal como lo habría escrito: con buena ortografía, tildes, mayúsculas, puntuación y gramática.\n\n"
        "Haz esto:\n"
        "1. Corrige ortografía, tildes, concordancia y palabras mal transcritas que se deduzcan por el contexto.\n"
        "2. Puntúa bien: separa con punto (o punto y coma) las oraciones independientes unidas solo por comas.\n"
        "3. Quita lo que en un texto escrito no estaría:\n"
        "   - Repeticiones involuntarias: «nadie nadie sabía» → «nadie sabía»; «fuimos a la a la playa» → "
        "«fuimos a la playa».\n"
        "   - Autocorrecciones: deja solo la versión buena. «a las ocho, no, a las nueve» → «a las nueve»; "
        "«el perro corría, corrían los perros» → «corrían los perros»; «la casa estaba en lo alto del, en "
        "lo alto de la colina» → «la casa estaba en lo alto de la colina».\n"
        "   - Arranques en falso: palabras sueltas que la persona abandonó para empezar de nuevo.\n"
        "   - Muletillas: «eh», «em», «este», «o sea», «bueno» cuando solo son relleno.\n\n"
        "No hagas esto:\n"
        "- No cambies el estilo ni el vocabulario, no uses sinónimos y no reordenes las frases.\n"
        "- No añadas ideas ni quites contenido. No resumas.\n"
        "- No quites las repeticiones con intención expresiva («que no, que no pensaba volver»).\n"
        "- Si una palabra es dudosa, déjala como está.\n\n" + _COMMON
    ),
    "poesia": (
        "Eres un corrector de poesía dictada. Respeta EXACTAMENTE los saltos de línea: devuelve el mismo número "
        "de versos, en el mismo orden, uno por línea. Corrige solo ortografía, tildes y palabras claramente mal "
        "transcritas. No toques el ritmo, la métrica, el orden de las palabras ni la puntuación expresiva. " + _COMMON
    ),
    "notas": (
        "Eres un corrector de notas dictadas. Si el texto enumera elementos («primero…, segundo…», «uno…, dos…», "
        "«comprar pan, leche y huevos»), conviértelos en una lista Markdown con «- » al principio de cada "
        "elemento, uno por línea. Las palabras que solo numeran («primero», «segundo», «uno», «dos») se quitan. "
        "Si hay una introducción («para mañana»), va en su propia línea antes de la lista. "
        "Corrige ortografía, tildes y palabras mal transcritas, y quita repeticiones involuntarias y muletillas "
        "(«eh», «este»). No resumas, no añadas elementos y no quites información.\n\n"
        "Ejemplo:\nEntrada: para el viaje primero sacar los billetes segundo reservar hotel y tercero avisar a ana\n"
        "Salida:\nPara el viaje:\n- Sacar los billetes.\n- Reservar hotel.\n- Avisar a Ana.\n\n" + _COMMON
    ),
}


_COMMON_EN = (
    "The text comes from an English speech recognizer. "
    "Return ONLY the corrected text: no quotes, no explanations, no headings and do not repeat the context."
)

PRESETS_EN = {
    "prosa": (
        "You are a proofreader for dictated text. You receive what someone said out loud and return the text as "
        "they would have written it: with correct spelling, capitalization, punctuation and grammar.\n\n"
        "Do this:\n"
        "1. Fix spelling, agreement and misrecognized words that can be worked out from the context.\n"
        "2. Punctuate properly: split independent sentences that are only joined by commas.\n"
        "3. Remove what would not be in a written text:\n"
        "   - Involuntary repetitions: «nobody nobody knew» → «nobody knew»; «we went to the to the beach» → "
        "«we went to the beach».\n"
        "   - Self-corrections: keep only the good version. «at eight, no, at nine» → «at nine»; «the dog was "
        "running, the dogs were running» → «the dogs were running».\n"
        "   - False starts: loose words the speaker abandoned to start again.\n"
        "   - Fillers: «uh», «um», «you know», «like» when they are only padding.\n\n"
        "Do not do this:\n"
        "- Do not change the style or the vocabulary, do not use synonyms and do not reorder sentences.\n"
        "- Do not add ideas or remove content. Do not summarize.\n"
        "- Do not remove repetitions that are meant for emphasis («no, no, I wasn't going back»).\n"
        "- If a word is doubtful, leave it as it is.\n\n" + _COMMON_EN
    ),
    "poesia": (
        "You are a proofreader for dictated poetry. Keep the line breaks EXACTLY: return the same number of lines, "
        "in the same order, one per line. Only fix spelling and clearly misrecognized words. Do not touch the "
        "rhythm, the meter, the word order or expressive punctuation. " + _COMMON_EN
    ),
    "notas": (
        "You are a proofreader for dictated notes. If the text lists items («first…, second…», «one…, two…», "
        "«buy bread, milk and eggs»), turn them into a Markdown list with «- » at the start of each item, one per "
        "line. Words that only number the items («first», «second», «one», «two») are removed. If there is an "
        "introduction («for tomorrow»), it goes on its own line before the list. Fix spelling and misrecognized "
        "words, and remove involuntary repetitions and fillers («uh», «um»). Do not summarize, do not add items "
        "and do not remove information.\n\n"
        "Example:\nInput: for the trip first get the tickets second book the hotel and third tell anna\n"
        "Output:\nFor the trip:\n- Get the tickets.\n- Book the hotel.\n- Tell Anna.\n\n" + _COMMON_EN
    ),
}

# Lo que se añade alrededor del texto, en cada idioma.
_FRAME = {
    "es": {
        "glossary": "Glosario (nombres propios y términos que deben escribirse exactamente así; si el reconocedor "
                    "escribió algo que suena parecido, corrígelo a la forma del glosario): ",
        "context": "Contexto anterior (YA corregido; NO lo modifiques ni lo devuelvas, es solo para entender "
                   "el texto):\n",
        "target": "Texto a corregir:\n",
        "hints": "Posibles repeticiones en ese texto. Si son involuntarias, deja solo la última; si son "
                 "expresivas, déjalas:\n",
    },
    "en": {
        "glossary": "Glossary (proper names and terms that must be written exactly like this; if the recognizer "
                    "wrote something that sounds similar, correct it to the glossary form): ",
        "context": "Previous context (ALREADY corrected; do NOT modify it or return it, it is only there to "
                   "understand the text):\n",
        "target": "Text to correct:\n",
        "hints": "Possible repetitions in that text. If they are involuntary, keep only the last one; if they are "
                 "meant for emphasis, keep them:\n",
    },
}


def presets(lang: str = "es") -> dict[str, str]:
    return PRESETS_EN if lang == "en" else PRESETS


def build_messages(mode: str, target: str, context: list[str], glossary: list[str], prompt: str = "",
                   lang: str = "es") -> list[dict]:
    """`prompt`: instrucciones propias del usuario para este modo (vacío: las de serie). El glosario, el contexto y
    las pistas de repeticiones se añaden igual. `lang`: idioma del dictado ("es" o "en")."""
    frame = _FRAME.get(lang, _FRAME["es"])
    system = prompt.strip() or presets(lang)[mode]
    terms = [t.strip() for t in glossary if t.strip()]
    if terms:
        system += "\n\n" + frame["glossary"] + ", ".join(terms) + "."
    parts = []
    if context:
        parts.append(frame["context"] + "\n\n".join(context))
    hints = []
    if mode != "poesia":
        # Los titubeos claros se arreglan antes (los modelos pequeños los arreglan al revés); los dudosos se señalan.
        target, hints = repair(target, lang)
    parts.append(frame["target"] + target)
    if hints:
        parts.append(frame["hints"] + "\n".join(f"«{h.text}» → «{h.fix}»" for h in hints))
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n---\n\n".join(parts)}]


def max_tokens_for(text: str, mode: str) -> int:
    # ≈ 3 caracteres por token en español; 1,5× de margen (2× en notas por las marcas de lista).
    factor = 2.0 if mode == "notas" else 1.5
    return max(64, int(len(text) / 3 * factor) + 32)
