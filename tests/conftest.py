import pytest


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """Los tests nunca tocan los ajustes ni la recuperación reales del usuario."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    import dictador.config as config
    import dictador.ui.main_window as main_window

    monkeypatch.setattr(config, "recovery_dir", lambda: tmp_path / "recovery")
    monkeypatch.setattr(main_window, "recovery_dir", lambda: tmp_path / "recovery")
