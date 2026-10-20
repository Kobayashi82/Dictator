"""Cola de corrección integrada en la ventana: LLM simulado y LLM caído."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from dictado.config import Settings


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, condition, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def make_window(settings, fake_llm):
    from dictado.ui.main_window import MainWindow

    window = MainWindow(settings, fake_asr=True, fake_llm=fake_llm)
    if fake_llm:
        window.corrector._client.delay = 0.05
    return window


def close(window):
    window.model.set_modified(False)
    window.close()


def test_paragraphs_get_corrected_in_order(app):
    window = make_window(Settings(), fake_llm=True)
    m = window.model
    m.append_sentence("nadie esperava la carta", "prosa")
    m.close_paragraph(correct=True)
    m.append_sentence("los vecinos salian", "prosa")
    m.close_paragraph(correct=True)
    m.append_sentence("sigo dictando", "prosa")
    assert wait(app, lambda: [p.status for p in m.paragraphs] == ["corrected", "corrected", "dictating"])
    assert [p.text for p in m.paragraphs[:2]] == ["Nadie esperaba la carta.", "Los vecinos salían."]
    assert m.paragraphs[0].raw == "nadie esperava la carta"
    close(window)


def test_user_edit_during_correction_wins(app):
    window = make_window(Settings(), fake_llm=True)
    window.corrector._client.delay = 0.5
    m = window.model
    p = m.append_sentence("texto original", "prosa")
    m.close_paragraph(correct=True)
    assert wait(app, lambda: p.status == "correcting")
    m.user_edit(p.id, "Lo he cambiado yo")
    time.sleep(0.6)
    wait(app, lambda: window.corrector.pending() == 0)
    app.processEvents()
    assert p.text == "Lo he cambiado yo" and p.status == "edited"
    close(window)


def test_mode_none_skips_llm(app):
    window = make_window(Settings(), fake_llm=True)
    m = window.model
    p = m.append_sentence("sin corregir", "ninguno")
    m.close_paragraph(correct=True)
    assert p.status == "closed"
    close(window)


def test_llm_down_keeps_raw_and_dictation_goes_on(app):
    settings = Settings(llm_base_url="http://127.0.0.1:9/v1", llm_model="x", llm_timeout_s=2)
    window = make_window(settings, fake_llm=False)
    m = window.model
    p = m.append_sentence("el servidor no responde", "prosa")
    m.close_paragraph(correct=True)
    assert wait(app, lambda: p.status == "rejected", seconds=20)
    assert p.text == "el servidor no responde"
    assert "conectar" in p.reason or "Error" in p.reason
    m.append_sentence("pero sigo dictando", "prosa")
    assert m.paragraphs[-1].status == "dictating"
    # Al volver el servidor, se puede reintentar.
    window.fake_llm = True
    window.configure_llm()
    window.corrector._client.delay = 0.01
    window.retry_failed()
    assert wait(app, lambda: p.status == "corrected")
    close(window)


def test_unconfigured_llm_closes_paragraphs(app):
    window = make_window(Settings(llm_model=""), fake_llm=False)
    p = window.model.append_sentence("hola", "prosa")
    window.model.close_paragraph(correct=True)
    assert p.status == "closed"
    close(window)
