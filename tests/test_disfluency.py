import pytest

from dictador.llm.disfluency import find_hesitations, repair
from dictador.llm.prompts import build_messages


@pytest.mark.parametrize(
    "said, written",
    [
        ("dejaban su paso a su paso ese olor", "dejaban a su paso ese olor"),
        ("los árboles se asombra, se asomaban por doquier", "los árboles se asomaban por doquier"),
        ("salía a las ocho, no, a las nueve de la mañana", "salía a las nueve de la mañana"),
        ("nadie nadie en la estación sabía, eh, sabía adónde iba", "nadie en la estación sabía adónde iba"),
        ("una casa en el en el campo", "una casa en el campo"),
        ("un huerto, este, muy grande", "un huerto, muy grande"),
        ("Ella ella se quedó callada.", "Ella se quedó callada."),
        ("Eh, empezamos.", "Empezamos."),
    ],
)
def test_clear_hesitations_are_repaired(said, written):
    out, doubtful = repair(said)
    assert out == written
    assert doubtful == []


@pytest.mark.parametrize(
    "text",
    [
        "En un lugar de la Mancha, de cuyo nombre no quiero acordarme, no ha mucho tiempo que vivía un hidalgo.",
        "Poco a poco se fue apagando la luz.",
        "Este perro es mío y esta casa también.",
        "Tenía una ama que pasaba de los cuarenta, y una sobrina que no llegaba a los veinte.",
        "Era la la nota más aguda.",  # palabras de dos letras: no se tocan
    ],
)
def test_normal_text_is_left_alone(text):
    assert repair(text) == (text, [])


def test_expressive_repetition_is_only_suggested():
    out, doubtful = repair("Le dijo que no, que no pensaba volver. Corre, corre.")
    assert out == "Le dijo que no, que no pensaba volver. Corre, corre."
    assert [h.text for h in doubtful] == ["que no, que no", "Corre, corre"]
    assert [h.fix for h in doubtful] == ["que no", "corre"]


def test_find_reports_positions():
    text = "dejaban su paso a su paso ese olor"
    (h,) = find_hesitations(text)
    assert text[h.start : h.end] == "su paso a su paso" and h.sure


def test_prompt_gets_repaired_text_and_doubts():
    msgs = build_messages("prosa", "nadie nadie lo sabía, que no, que no", [], [])
    user = msgs[1]["content"]
    assert "Texto a corregir:\nnadie lo sabía, que no, que no" in user
    assert "«que no, que no» → «que no»" in user


def test_poetry_is_not_repaired():
    msgs = build_messages("poesia", "verde verde\nverde viento", [], [])
    assert msgs[1]["content"].endswith("verde verde\nverde viento")
