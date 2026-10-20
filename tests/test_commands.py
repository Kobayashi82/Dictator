import pytest

from dictado.commands import DeleteLastSentence, NewParagraph, Text, Title, fold, parse, phonetic_key


def test_fold_and_key():
    assert fold("¡Punto y Aparte!") == "punto y aparte"
    assert phonetic_key("cebolla") == phonetic_key("sebolla")
    assert phonetic_key("vaca") == phonetic_key("baca")
    assert phonetic_key("hola") == phonetic_key("ola")
    assert phonetic_key("queso") == phonetic_key("keso")


@pytest.mark.parametrize(
    "said",
    ["Punto y aparte.", "punto y aparte", "Punto y a parte.", "Puntoy aparte", "Nuevo párrafo.", "Nueva estrofa."],
)
def test_new_paragraph(said):
    assert parse(said) == [NewParagraph()]


@pytest.mark.parametrize("said", ["Borra la última frase.", "Borrar la última frase", "borra la ultima frace"])
def test_delete_last(said):
    assert parse(said) == [DeleteLastSentence()]


def test_command_at_end_of_sentence():
    assert parse("Y se fue sin decir nada. Punto y aparte.") == [Text("Y se fue sin decir nada."), NewParagraph()]
    assert parse("y se fue, punto y aparte") == [Text("y se fue"), NewParagraph()]


def test_title():
    assert parse("Título: el viejo y el mar.") == [Title("El viejo y el mar")]
    assert parse("Título, capítulo uno.") == [Title("Capítulo uno")]
    assert parse("Título") == [Text("Título")]


@pytest.mark.parametrize(
    "said",
    [
        "El punto de partida fue aparte.",
        "Le dijo que borrara la carta.",
        "Tuvo un nuevo pariente.",
        "Era una mañana tranquila en el pueblo.",
        "Los títulos de la biblioteca.",
        "Títulos y honores no le importaban.",
        "Titular de la noticia.",
    ],
)
def test_normal_sentences_are_text(said):
    assert parse(said) == [Text(said)]


def test_split_verses():
    from dictado.commands import split_verses

    assert split_verses("Verde que te quiero verde. Verde viento verdes ramas. El barco sobre la mar.") == [
        "Verde que te quiero verde.",
        "Verde viento verdes ramas.",
        "El barco sobre la mar.",
    ]
    assert split_verses("Ay, qué dolor, ay. ¡Me muero!") == ["Ay, qué dolor, ay.", "¡Me muero!"]
    assert split_verses("Llegó el Sr. García a caballo.") == ["Llegó el Sr. García a caballo."]
    assert split_verses("verso sin punto final") == ["verso sin punto final"]
