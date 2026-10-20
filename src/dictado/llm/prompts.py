"""Prompts por modo de corrección."""

from __future__ import annotations

_COMMON = (
    "El texto viene de un reconocedor de voz en español. "
    "Devuelve SOLO el texto corregido: sin comillas, sin explicaciones, sin encabezados y sin repetir el contexto."
)

PRESETS = {
    "prosa": (
        "Eres un corrector de textos dictados. Corrige ortografía, tildes, puntuación, mayúsculas, concordancia "
        "y palabras mal transcritas que se deduzcan claramente por el contexto. "
        "No cambies el estilo, el vocabulario ni el orden de las palabras. No añadas ni quites ideas. "
        "No resumas ni reescribas. Si una palabra es dudosa, déjala como está. " + _COMMON
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
        "Corrige ortografía, tildes y palabras mal transcritas. No resumas, no añadas elementos y no quites "
        "información.\n\n"
        "Ejemplo:\nEntrada: para el viaje primero sacar los billetes segundo reservar hotel y tercero avisar a ana\n"
        "Salida:\nPara el viaje:\n- Sacar los billetes.\n- Reservar hotel.\n- Avisar a Ana.\n\n" + _COMMON
    ),
}


def build_messages(mode: str, target: str, context: list[str], glossary: list[str]) -> list[dict]:
    system = PRESETS[mode]
    terms = [t.strip() for t in glossary if t.strip()]
    if terms:
        system += (
            "\n\nGlosario (nombres propios y términos que deben escribirse exactamente así; si el reconocedor "
            "escribió algo que suena parecido, corrígelo a la forma del glosario): " + ", ".join(terms) + "."
        )
    parts = []
    if context:
        parts.append(
            "Contexto anterior (YA corregido; NO lo modifiques ni lo devuelvas, es solo para entender el texto):\n"
            + "\n\n".join(context)
        )
    parts.append("Texto a corregir:\n" + target)
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n---\n\n".join(parts)}]


def max_tokens_for(text: str, mode: str) -> int:
    # ≈ 3 caracteres por token en español; 1,5× de margen (2× en notas por las marcas de lista).
    factor = 2.0 if mode == "notas" else 1.5
    return max(64, int(len(text) / 3 * factor) + 32)
