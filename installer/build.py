"""Genera dist/Dictador (PyInstaller) y dist/Instalar Dictador.exe (Inno Setup).

Uso: uv run python installer/build.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_iscc() -> Path:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    ]
    found = shutil.which("ISCC") or next((str(c) for c in candidates if c.is_file()), None)
    if not found:
        sys.exit("No se encuentra Inno Setup 6 (ISCC.exe). Instálalo con: winget install JRSoftware.InnoSetup")
    return Path(found)


def version() -> str:
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return "1.0.0"


def main() -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", "dictador.spec", "--noconfirm"], cwd=ROOT, check=True)
    iscc = find_iscc()
    subprocess.run([str(iscc), f"/DAppVersion={version()}", str(ROOT / "installer" / "dictador.iss")], cwd=ROOT, check=True)
    print(f"Listo: {ROOT / 'dist' / 'Instalar Dictador.exe'}")


if __name__ == "__main__":
    main()
