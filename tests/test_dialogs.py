"""Todos los diálogos se construyen y los ajustes vuelven tal cual (sin abrir ventanas)."""

import os
import pkgutil
import importlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import dictador
from dictador.config import Settings


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_every_module_imports():
    for module in pkgutil.walk_packages(dictador.__path__, "dictador."):
        if module.name != "dictador.__main__":
            importlib.import_module(module.name)


def test_settings_dialog_roundtrip(app, tmp_path):
    from dictador.ui.settings import SettingsDialog

    original = Settings(
        models_dir=str(tmp_path),
        managed_enabled=True,
        managed_device="gpu",
        managed_gpu_layers=40,
        llm_model="qwen",
        glossary=["Macondo"],
        theme="oscuro",
    )
    dialog = SettingsDialog(original)
    assert dialog.result_settings() == original
    dialog.where.set_current("cpu")
    assert dialog.result_settings().managed_device == "cpu"
    dialog.paragraph_pause.set_current("4000")
    dialog.theme.set_current("claro")
    new = dialog.result_settings()
    assert new.long_pause_ms == 4000 and new.theme == "claro"


def test_settings_dialog_keeps_external_server(app):
    from dictador.ui.settings import SettingsDialog

    original = Settings(managed_enabled=False, llm_model="qwen3.5-4b", long_pause_ms=2700)
    dialog = SettingsDialog(original)
    assert dialog.where.current() == "externo"
    assert dialog.result_settings() == original  # 2700 ms no es una de las tres opciones, pero se respeta
    dialog.where.set_current("gpu")
    new = dialog.result_settings()
    assert new.managed_enabled and new.managed_device == "gpu"


def test_theme_switch_changes_colors(app):
    from dictador.ui import style
    from dictador.ui.theme import apply_theme

    apply_theme("oscuro")
    assert style.DARK and style.PAGE.lightness() < 80
    assert style.PAGE.name() in app.styleSheet()
    apply_theme("claro")
    assert not style.DARK and style.PAGE.name().lower() == "#ffffff"


def test_other_dialogs(app, tmp_path):
    from dictador.ui.dialogs import DiffDialog, GlossaryDialog, diff_html
    from dictador.ui.models_dialog import ModelsDialog

    DiffDialog("hola que tal", "Hola, ¿qué tal?")
    assert GlossaryDialog(["a", "b"]).terms() == ["a", "b"]
    dialog = ModelsDialog(tmp_path, first_run=True)
    assert dialog.download_button.isEnabled()
    assert "line-through" in diff_html("uno dos", "uno tres")


def test_settings_wheel_scrolls_page_not_controls(app):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    from dictador.ui.settings import SettingsDialog

    dialog = SettingsDialog(Settings())
    dialog.device.addItem("Otro micrófono", "otro")
    combo, spin = dialog.device, dialog.autosave
    before = (combo.currentIndex(), spin.value())
    for widget in (combo, spin):
        event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(widget, event)
        assert not event.isAccepted()  # pasa a la página, que se desplaza
    assert (combo.currentIndex(), spin.value()) == before


def test_settings_custom_prompt_edit_and_restore(app):
    from dictador.llm.prompts import PRESETS
    from dictador.ui.settings import SettingsDialog

    original = Settings(custom_prompts={"poesia": "Corrige solo las tildes."})
    dialog = SettingsDialog(original)
    assert dialog.result_settings() == original
    assert dialog.prompt.toPlainText() == PRESETS["prosa"] and not dialog.prompt_reset.isEnabled()
    dialog.prompt.setPlainText("Corrige como un profesor de lengua.")
    dialog.prompt_mode.setCurrentIndex(dialog.prompt_mode.findData("poesia"))
    assert dialog.prompt.toPlainText() == "Corrige solo las tildes." and dialog.prompt_reset.isEnabled()
    dialog.prompt_reset.click()
    assert dialog.prompt.toPlainText() == PRESETS["poesia"]
    assert dialog.result_settings().custom_prompts == {"prosa": "Corrige como un profesor de lengua."}
