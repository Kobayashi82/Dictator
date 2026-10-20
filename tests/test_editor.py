"""Sincronización editor ↔ modelo, sin ventana (QT_QPA_PLATFORM=offscreen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from dictado.doc.model import DocumentModel, Paragraph
from dictado.ui.editor import DictationEditor, diff_ranges


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ed(app):
    model = DocumentModel()
    editor = DictationEditor(model)
    return model, editor


def blocks(editor):
    out = []
    b = editor.document().firstBlock()
    while b.isValid():
        out.append(b.text().replace(" ", "\n"))
        b = b.next()
    return out


def type_at(editor, position, text, select_to=None):
    c = QTextCursor(editor.document())
    c.setPosition(position)
    if select_to is not None:
        c.setPosition(select_to, QTextCursor.MoveMode.KeepAnchor)
    c.insertText(text)
    editor.reconcile()


def test_dictation_appends_and_closes(ed):
    model, editor = ed
    model.append_sentence("Hola.", "prosa")
    model.append_sentence("Qué tal.", "prosa")
    assert blocks(editor) == ["Hola. Qué tal."]
    model.close_paragraph(correct=True)
    model.append_sentence("Otro.", "prosa")
    assert blocks(editor) == ["Hola. Qué tal.", "Otro."]
    assert [p.status for p in model.paragraphs] == ["pending", "dictating"]


def test_poetry_lines_stay_in_one_block(ed):
    model, editor = ed
    model.append_sentence("Verde que te quiero verde", "poesia")
    model.append_sentence("verde viento", "poesia")
    assert editor.document().blockCount() == 1
    assert blocks(editor) == ["Verde que te quiero verde\nverde viento"]


def test_correction_replaces_text(ed):
    model, editor = ed
    p = model.append_sentence("era una vez", "prosa")
    model.close_paragraph(correct=True)
    model.set_status(p.id, "correcting")
    assert model.apply_correction(p.id, "era una vez", "Era una vez.")
    assert blocks(editor) == ["Era una vez."]
    model.revert(p.id)
    assert blocks(editor) == ["era una vez"]


def test_user_edit_marks_paragraph(ed):
    model, editor = ed
    p = model.append_sentence("Uno.", "prosa")
    model.close_paragraph(correct=True)
    model.append_sentence("Dos.", "prosa")
    type_at(editor, 0, "X")
    assert p.user_edited and p.text == "XUno."
    assert p.status == "edited"
    # Una corrección que llega tarde se descarta.
    assert not model.apply_correction(p.id, "Uno.", "UNO.")
    assert blocks(editor) == ["XUno.", "Dos."]


def test_user_split_and_merge(ed):
    model, editor = ed
    model.append_sentence("Primera frase. Segunda frase.", "prosa")
    model.close_paragraph(correct=False)
    type_at(editor, len("Primera frase."), "\n", select_to=len("Primera frase. "))
    assert [p.text for p in model.paragraphs] == ["Primera frase.", "Segunda frase."]
    assert len({p.id for p in model.paragraphs}) == 2
    # Unir de nuevo: el segundo párrafo desaparece del modelo.
    type_at(editor, len("Primera frase."), " ", select_to=len("Primera frase.") + 1)
    assert [p.text for p in model.paragraphs] == ["Primera frase. Segunda frase."]


def test_typing_after_dictating_paragraph_closes_it(ed):
    model, editor = ed
    p = model.append_sentence("Dictando.", "prosa")
    end = editor.document().characterCount() - 1
    type_at(editor, end, "\nEscrito a mano")
    assert p.status == "pending"
    assert model.paragraphs[-1].text == "Escrito a mano"
    # El siguiente dictado va a un párrafo nuevo, al final.
    model.append_sentence("Más dictado.", "prosa")
    assert blocks(editor) == ["Dictando.", "Escrito a mano", "Más dictado."]


def test_dictation_reuses_trailing_empty_line(ed):
    model, editor = ed
    model.append_sentence("Uno.", "prosa")
    model.close_paragraph(correct=False)
    type_at(editor, editor.document().characterCount() - 1, "\n")
    assert len(model.paragraphs) == 2
    model.append_sentence("Dos.", "prosa")
    assert blocks(editor) == ["Uno.", "Dos."]
    assert model.paragraphs[-1].status == "dictating" and not model.paragraphs[-1].user_edited


def test_dictation_keeps_user_cursor(ed):
    model, editor = ed
    model.append_sentence("Uno.", "prosa")
    model.close_paragraph(correct=False)
    model.append_sentence("Dos.", "prosa")
    cursor = editor.textCursor()
    cursor.setPosition(2)
    editor.setTextCursor(cursor)
    model.append_sentence("Tres.", "prosa")
    assert editor.textCursor().position() == 2


def test_delete_everything(ed):
    model, editor = ed
    model.append_sentence("Uno.", "prosa")
    model.close_paragraph(correct=False)
    model.append_sentence("Dos.", "prosa")
    type_at(editor, 0, "", select_to=editor.document().characterCount() - 1)
    assert [p.text for p in model.paragraphs if p.text] == []
    model.append_sentence("Nuevo.", "prosa")
    assert [b for b in blocks(editor) if b] == ["Nuevo."]


def test_rebuild_from_loaded_document(ed):
    model, editor = ed
    model.load([Paragraph(raw="Título", status="closed", style="title"), Paragraph(raw="a\nb", mode="poesia", status="closed")])
    assert blocks(editor) == ["Título", "a\nb"]
    model.remove(model.paragraphs[0].id)
    assert blocks(editor) == ["a\nb"]


def test_delete_last_sentence(ed):
    model, editor = ed
    model.append_sentence("Uno.", "prosa")
    model.append_sentence("Dos.", "prosa")
    assert model.delete_last_sentence()
    assert blocks(editor) == ["Uno."]


def test_diff_ranges():
    old = "hola que tal estas"
    new = "Hola, ¿qué tal estás?"
    ranges = diff_ranges(old, new)
    changed = [new[a:b] for a, b in ranges]
    assert "tal" not in " ".join(changed)
    assert any("qué" in c for c in changed)
