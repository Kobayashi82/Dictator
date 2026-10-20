"""Diálogos pequeños: ver cambios y glosario del documento."""

from __future__ import annotations

import difflib
import html
import re

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QTextBrowser, QVBoxLayout

_TOKENS = re.compile(r"\s+|[^\s]+")


def diff_html(old: str, new: str, dark: bool = False) -> str:
    """Diferencias palabra a palabra: lo quitado tachado en rojo, lo añadido en verde."""
    a = _TOKENS.findall(old)
    b = _TOKENS.findall(new)
    out = []
    removed = "#5a2a2a" if dark else "#fbd5d5"
    added = "#2a4a2a" if dark else "#d3f2cf"

    def esc(tokens):
        return html.escape("".join(tokens)).replace("\n", "<br>")

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(esc(a[i1:i2]))
            continue
        if i2 > i1:
            out.append(f'<span style="background:{removed};text-decoration:line-through">{esc(a[i1:i2])}</span>')
        if j2 > j1:
            out.append(f'<span style="background:{added}">{esc(b[j1:j2])}</span>')
    return "".join(out)


class DiffDialog(QDialog):
    def __init__(self, raw: str, corrected: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cambios del corrector")
        self.resize(640, 380)
        dark = self.palette().base().color().lightness() < 128
        view = QTextBrowser(self)
        view.setHtml(
            '<p style="font-size:13pt;line-height:140%">' + diff_html(raw, corrected, dark) + "</p>"
            "<hr><p><b>Original (Parakeet):</b><br>" + html.escape(raw).replace("\n", "<br>") + "</p>"
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(view)
        layout.addWidget(buttons)


class GlossaryDialog(QDialog):
    def __init__(self, terms: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Glosario del documento")
        self.resize(420, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Nombres de personajes, lugares y vocabulario raro de este documento, uno por línea.\n"
                "Se guardan con el proyecto y se suman al glosario general."
            )
        )
        self.edit = QPlainTextEdit("\n".join(terms))
        layout.addWidget(self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def terms(self) -> list[str]:
        return [t.strip() for t in self.edit.toPlainText().splitlines() if t.strip()]
