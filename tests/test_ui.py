"""Interfaz sencilla: ventana, componentes animados y asistente de la primera vez (sin pantalla)."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from dictador.config import Settings
from dictador.doc.model import Paragraph


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    from dictador.ui.main_window import MainWindow

    w = MainWindow(Settings(onboarding_done=True), fake_asr=True, fake_llm=True)
    yield w
    w.model.set_modified(False)
    w.close()


def pump(app, seconds=0.3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_mode_buttons_change_mode(window):
    window.set_mode("poesia")
    assert window.model.mode == "poesia"
    assert window.mode_control.current() == "poesia"
    assert window.settings.mode == "poesia"


def test_font_size_steps(window):
    window.settings.font_size = 18
    window.change_font(+1)
    assert window.settings.font_size == 20
    window.change_font(-1)
    window.change_font(-1)
    assert window.settings.font_size == 16
    assert window.editor.document().defaultFont().pointSize() == 16


def test_dictation_button_states(app, window):
    mic = window.canvas.mic
    assert mic.state == "idle"
    window.toggle_dictation()
    pump(app, 0.5)
    assert mic.state == "listening"
    window.toggle_dictation()
    pump(app, 0.5)
    assert mic.state == "idle"


def test_printable_document_has_clean_text(window):
    window.model.load([Paragraph(raw="Título", style="title", status="closed"), Paragraph(raw="Uno <dos>\ntres", status="closed")])
    window.editor.set_partial("esto no se imprime")
    text = window.printable_document().toPlainText()
    assert "Título" in text and "Uno <dos>" in text and "tres" in text
    assert "esto no se imprime" not in text


def test_more_menu_lists_advanced_options(window):
    panel = window.more_menu()
    texts = panel.texts()
    assert "Ajustes" in texts and "Ayuda" in texts and "Salir" in texts
    assert "Marcar lo que se ha corregido" in texts
    assert "Reintentar los párrafos sin corregir" not in texts  # solo aparece si hay alguno
    panel.close()


def test_corrected_paragraph_flashes(app, window):
    m = window.model
    p = m.append_sentence("nadie esperava", "prosa")
    m.close_paragraph(correct=True)
    deadline = time.monotonic() + 10
    while p.status != "corrected" and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert p.status == "corrected"
    pump(app, 0.1)
    assert window.editor.extraSelections()  # el destello verde está en marcha


def test_onboarding_walkthrough(app, window):
    from dictador.ui.onboarding import Onboarding

    wizard = Onboarding(window)
    assert wizard.forward.text() == "Empezar"
    wizard.next()  # descarga: con --fake-asr no hay nada que bajar
    pump(app, 0.2)
    assert wizard.current().can_continue()
    wizard.next()  # prueba del micrófono
    assert window.suppress_dictation
    wizard.current().toggle()
    pump(app, 2.0)
    assert "El micrófono funciona" in wizard.current().feedback.text()
    assert window.model.paragraphs == []  # la prueba no escribe en el documento
    wizard.next()
    assert not window.suppress_dictation and not window.engine.running
    wizard.next()
    assert wizard.forward.text() == "Empezar a escribir"
    wizard.next()
    assert window.settings.onboarding_done
    assert window.settings.managed_enabled and window.settings.managed_device == "cpu"


def test_intro_only_has_two_pages(window):
    from dictador.ui.onboarding import Onboarding

    window.settings.onboarding_done = False
    wizard = Onboarding(window, intro_only=True)
    assert len(wizard.pages) == 2
    wizard.next()
    wizard.next()
    assert not window.settings.onboarding_done  # repasar la explicación no cuenta como instalación


def test_segmented_and_dialog_widgets(app):
    from dictador.ui.widgets import FriendlyDialog, SegmentedControl

    seg = SegmentedControl([("a", "Uno", ""), ("b", "Dos", "")])
    got = []
    seg.changed.connect(got.append)
    seg.show()
    seg.set_current("b", animate=False)
    assert seg.current() == "b"
    dialog = FriendlyDialog(None, "Título", "Texto", ["Sí", "No"])
    dialog._pick(1)
    assert dialog._choice == 1


def test_custom_prompt_reaches_the_corrector(window):
    jobs = []
    window.corrector.enqueue = jobs.append
    window.settings.custom_prompts = {"prosa": "Instrucciones propias."}
    p = window.model.append_sentence("hola", "prosa")
    window.model.close_paragraph(correct=True)
    assert jobs and jobs[0].pid == p.id and jobs[0].prompt == "Instrucciones propias."
