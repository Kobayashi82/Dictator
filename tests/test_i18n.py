"""Idioma: todos los textos tienen traducción inglesa y el dictado funciona en inglés."""

import ast
import os
import pathlib
import re
import string

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import dictador
from dictador import commands, i18n
from dictador.i18n_en import EN

SRC = pathlib.Path(dictador.__file__).parent


def marked_strings() -> dict[str, str]:
    """Textos dentro de tr("…") o N_("…") en el código → fichero donde aparecen."""
    found = {}
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, path.name)
    return found


def fields(text: str) -> set[str]:
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name}


@pytest.fixture
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("es")


def test_every_text_has_an_english_translation():
    marked = marked_strings()
    missing = sorted(f"{file}: {text!r}" for text, file in marked.items() if text not in EN)
    assert not missing, "Faltan traducciones:\n" + "\n".join(missing)
    unused = sorted(set(EN) - set(marked))
    assert not unused, "Traducciones que ya no se usan:\n" + "\n".join(map(repr, unused))


def test_translations_keep_the_placeholders():
    wrong = [k for k, v in EN.items() if fields(k) != fields(v)]
    assert not wrong, wrong


def test_tr_switches_language(english):
    assert i18n.tr("Guardar") == "Save"
    assert i18n.tr("Tamaño de letra: {size}", size=20) == "Text size: 20"
    i18n.set_language("es")
    assert i18n.tr("Tamaño de letra: {size}", size=20) == "Tamaño de letra: 20"


def test_english_voice_commands():
    assert commands.parse("New paragraph.", "en") == [commands.NewParagraph()]
    assert commands.parse("Delete the last sentence.", "en") == [commands.DeleteLastSentence()]
    assert commands.parse("Title the storm", "en") == [commands.Title("The storm")]
    assert commands.parse("And then she left. New paragraph.", "en") == [
        commands.Text("And then she left."), commands.NewParagraph()]
    assert commands.parse("Titles are hard.", "en") == [commands.Text("Titles are hard.")]
    # En español, las órdenes inglesas son texto normal (y al revés).
    assert commands.parse("New paragraph.", "es") == [commands.Text("New paragraph.")]
    assert commands.parse("Punto y aparte.", "en") == [commands.Text("Punto y aparte.")]


def test_english_corrector_prompt_and_fillers():
    from dictador.llm.disfluency import repair
    from dictador.llm.prompts import build_messages

    msgs = build_messages("prosa", "we went to the um beach", ["Before."], ["Macondo"], lang="en")
    assert msgs[0]["content"].startswith("You are a proofreader") and "Glossary" in msgs[0]["content"]
    assert "Text to correct:\nwe went to the beach" in msgs[1]["content"]
    assert "Previous context" in msgs[1]["content"]
    assert repair("put it on the table, no, on the chair", "en")[0] == "put it on the chair"
    assert repair("Um, we started", "en")[0] == "We started"
    assert repair("I like it", "en")[0] == "I like it"  # «like» solo se quita suelto entre comas


def test_window_in_english(english):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from dictador.config import Settings
    from dictador.ui.main_window import MainWindow

    w = MainWindow(Settings(onboarding_done=True), fake_asr=True, fake_llm=True)
    try:
        assert w.act_save.text() == "Save"
        assert w.mode_control._options[0][1] == "Text"
        assert w.canvas.paragraph.text() == "New paragraph"
        assert "Settings" in w.more_menu().texts()
        assert re.search(r"Start or stop talking", w.canvas.mic.toolTip())
    finally:
        w.model.set_modified(False)
        w.close()


def test_old_custom_prompts_are_spanish(tmp_path):
    import json

    from dictador.config import Settings

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"custom_prompts": {"prosa": "Solo tildes.", "en/notas": "Only commas."}}), "utf-8")
    assert Settings.load(path).custom_prompts == {"es/prosa": "Solo tildes.", "en/notas": "Only commas."}
