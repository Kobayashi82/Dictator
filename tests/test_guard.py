import pytest

from dictador.llm.guard import clean_output, levenshtein, validate
from dictador.llm.prompts import build_messages, max_tokens_for

RAW = "nadie esperava la carta que llego ese dia el cartero la dejo en la puerta de la iglesia"
GOOD = "Nadie esperaba la carta que llegó ese día. El cartero la dejó en la puerta de la iglesia."


def test_levenshtein():
    assert levenshtein("", "abc") == 3
    assert levenshtein("casa", "cosa") == 1
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("abc", "abc") == 0


def test_good_correction_is_accepted():
    r = validate(RAW, GOOD, "prosa")
    assert r.ok, r.reason
    assert r.text == GOOD


@pytest.mark.parametrize(
    "output",
    [
        f"Aquí tienes el texto corregido:\n\n{GOOD}",
        f"Claro, aquí está la versión corregida:\n{GOOD}",
        f"Texto corregido: {GOOD}",
        f"«{GOOD}»",
        f'"{GOOD}"',
        f"```\n{GOOD}\n```",
        f"<texto>{GOOD}</texto>",
        f"<think>Voy a corregir las tildes.</think>\n{GOOD}",
        f"razonamiento sin abrir</think>{GOOD}",
    ],
)
def test_wrappers_are_cleaned(output):
    r = validate(RAW, output, "prosa")
    assert r.ok, r.reason
    assert r.text == GOOD


def test_quotes_kept_when_original_had_them():
    raw = "«hola que tal»"
    assert clean_output("«Hola, ¿qué tal?»", raw) == "«Hola, ¿qué tal?»"


def test_inner_dialogue_quotes_are_not_stripped():
    out = "«Ven», dijo ella. «Ahora»"
    assert clean_output(out, "ven dijo ella ahora") == out


def test_rewrite_is_rejected():
    rewrite = "Un cartero mayor dejó una carta inesperada junto a la iglesia, y nadie en el pueblo la esperaba."
    r = validate(RAW, rewrite, "prosa")
    assert not r.ok
    assert r.reason


def test_length_change_is_rejected():
    longer = GOOD + " Y entonces todo el pueblo se reunió para leerla en voz alta delante del alcalde."
    r = validate(RAW, longer, "prosa")
    assert not r.ok and "Añade" in r.reason
    r = validate("verde que te quiero", "verde que te quiero verde viento verdes ramas", "poesia")
    assert not r.ok and "longitud" in r.reason


def test_summary_is_rejected():
    assert not validate(RAW, "Llegó una carta.", "prosa").ok


def test_empty_output_is_rejected():
    assert not validate(RAW, "   ", "prosa").ok
    assert not validate(RAW, "<think>solo pienso</think>", "prosa").ok


def test_short_texts_have_absolute_margin():
    assert validate("hola que tal", "Hola, ¿qué tal?", "prosa").ok


def test_thresholds_are_configurable():
    out = "Nadie aguardaba aquella misiva que llegó ese día. El cartero la dejó en la puerta de la iglesia."
    assert validate(RAW, out, "prosa", max_distance=0.3).ok
    assert not validate(RAW, out, "prosa", max_distance=0.05).ok
    cleaned = "El tren salía a las nueve."
    assert validate("el tren salía a las ocho no a las nueve", cleaned, "prosa", max_removed=0.5).ok
    assert not validate("el tren salía a las ocho no a las nueve", cleaned, "prosa", max_removed=0.2).ok


@pytest.mark.parametrize(
    "raw, out",
    [
        (
            "El tren salía a las ocho, no, a las nueve de la mañana y nadie nadie en la estación sabía, eh, "
            "sabía adónde iba.",
            "El tren salía a las nueve de la mañana y nadie en la estación sabía adónde iba.",
        ),
        (
            "Mi abuela tenía una casa en el en el campo con un huerto, este, muy grande.",
            "Mi abuela tenía una casa en el campo con un huerto muy grande.",
        ),
        (
            "Los árboles verdes se asombra, se asomaban por doquier.",
            "Los árboles verdes se asomaban por doquier.",
        ),
        (
            "hacía fresco y los árboles comenzaban a adquirir un color verde todo se observaba limpio",
            "Hacía fresco, y los árboles comenzaban a adquirir un color verde; todo se observaba limpio.",
        ),
    ],
)
def test_disfluency_cleanup_is_accepted(raw, out):
    r = validate(raw, out, "prosa")
    assert r.ok, r.reason


def test_word_changes_ignores_transcription_typos():
    from dictador.llm.guard import word_changes

    assert word_changes("nadie esperava la carta", "Nadie esperaba la carta.") == (0, 0, 4)
    assert word_changes("nadie nadie sabía", "Nadie sabía.") == (0, 1, 3)
    assert word_changes("la carta", "la misiva") == (1, 1, 2)


def test_poetry_line_count_must_match():
    raw = "verde que te quiero verde\nverde viento verdes ramas\nel barco sobre la mar"
    ok = "Verde que te quiero verde,\nverde viento, verdes ramas,\nel barco sobre la mar."
    assert validate(raw, ok, "poesia").ok
    merged = "Verde que te quiero verde, verde viento, verdes ramas,\nel barco sobre la mar."
    r = validate(raw, merged, "poesia")
    assert not r.ok and "versos" in r.reason


def test_poetry_ignores_blank_lines_in_output():
    raw = "uno dos\ntres cuatro"
    assert validate(raw, "Uno, dos,\n\ntres, cuatro.", "poesia").text == "Uno, dos,\ntres, cuatro."


def test_notes_list_conversion_is_accepted():
    raw = "comprar pan leche huevos y llamar al fontanero"
    out = "- Comprar pan\n- Leche\n- Huevos\n- Llamar al fontanero"
    r = validate(raw, out, "notas")
    assert r.ok, r.reason


def test_prompt_contains_context_glossary_and_target():
    msgs = build_messages("prosa", "texto nuevo", ["Párrafo anterior."], ["Macondo", "Aureliano"])
    assert msgs[0]["role"] == "system"
    assert "Macondo, Aureliano" in msgs[0]["content"]
    assert "Párrafo anterior." in msgs[1]["content"]
    assert msgs[1]["content"].rstrip().endswith("texto nuevo")
    assert "NO lo modifiques" in msgs[1]["content"]


def test_max_tokens_scales():
    assert max_tokens_for("x" * 300, "prosa") == 182
    assert max_tokens_for("x" * 300, "notas") > max_tokens_for("x" * 300, "prosa")
    assert max_tokens_for("hola", "prosa") == 64


def test_notes_spoken_numbering_is_not_a_change():
    raw = "para mañana primero comprar pan y leche segundo llamar al fontanero tercero enviar el informe a marta"
    out = "Para mañana:\n- Comprar pan y leche.\n- Llamar al fontanero.\n- Enviar el informe a Marta."
    assert validate(raw, out, "notas").ok
    assert not validate(raw, "Para mañana:\n- Comprar pan.", "notas").ok
