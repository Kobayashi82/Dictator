# PyInstaller: `uv run pyinstaller dictador.spec --noconfirm` → dist/Dictador/Dictador.exe
# Los modelos NO van dentro: se descargan desde la app a %LOCALAPPDATA%\Dictador\models.

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = collect_data_files("onnx_asr")  # preprocesadores ONNX de onnx-asr
datas += copy_metadata("onnx-asr")  # onnx_asr lee su versión con importlib.metadata
datas += collect_data_files("docx")  # plantilla por defecto de python-docx

a = Analysis(
    ["src/dictador/__main__.py"],
    pathex=["src"],
    datas=datas,
    hiddenimports=["dictador.app"],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dictador",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Dictador", upx=False)
