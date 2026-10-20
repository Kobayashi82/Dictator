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
    dialog.source.setCurrentIndex(1)
    assert not dialog.managed.isEnabled() and dialog.external.isEnabled()
    assert dialog.result_settings().managed_enabled is False


def test_other_dialogs(app, tmp_path):
    from dictador.ui.dialogs import DiffDialog, GlossaryDialog, diff_html
    from dictador.ui.models_dialog import ModelsDialog

    DiffDialog("hola que tal", "Hola, ¿qué tal?")
    assert GlossaryDialog(["a", "b"]).terms() == ["a", "b"]
    dialog = ModelsDialog(tmp_path, first_run=True)
    assert dialog.download_button.isEnabled()
    assert "line-through" in diff_html("uno dos", "uno tres")
