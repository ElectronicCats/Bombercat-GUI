"""Copia con Ctrl+C para widgets que **no** soportan selección de texto con el
ratón.

En Textual, la selección de texto (arrastrar + Ctrl+C) funciona en widgets que
renderizan texto plano — `Static`, `Label`, `RichLog`, `Input`— pero **no** en
`Tree` ni `DataTable` (traen `ALLOW_SELECT=False` porque su render por líneas no
expone texto extraíble). Para que "seleccionar y Ctrl+C" funcione en toda la
TUI, estos widgets ofrecen copia explícita del elemento resaltado (fila/celda),
cediendo a la copia de selección de texto estándar cuando el usuario sí tiene
una selección activa en pantalla.
"""
from __future__ import annotations

from textual.actions import SkipAction
from textual.binding import Binding
from textual.widgets import DataTable


def short(text: str, n: int = 48) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[:n] + "…"


def cell_text(cell) -> str:
    """Texto plano de una celda (str o `rich.text.Text`)."""
    plain = getattr(cell, "plain", None)
    return plain if plain is not None else str(cell)


def has_text_selection(widget) -> bool:
    """¿Hay una selección de texto activa en la pantalla? (para cederle Ctrl+C)."""
    try:
        return bool(widget.screen.get_selected_text())
    except Exception:
        return False


class CopyableDataTable(DataTable):
    """`DataTable` cuyo Ctrl+C copia la **fila resaltada** al portapapeles.

    Si hay una selección de texto en pantalla, deja pasar el evento para que la
    copie el manejador estándar (`screen.copy_text`); si no hay ni selección ni
    fila, también lo deja pasar (acaba en el aviso "pulsa q para salir")."""

    BINDINGS = [Binding("ctrl+c", "copy_row", "Copiar fila", show=False)]

    def action_copy_row(self) -> None:
        if has_text_selection(self):
            raise SkipAction()
        try:
            if self.row_count == 0:
                raise SkipAction()
            row = self.get_row_at(self.cursor_row)
        except SkipAction:
            raise
        except Exception:
            raise SkipAction()
        text = "  ".join(cell_text(c) for c in row).strip()
        if not text:
            raise SkipAction()
        self.app.copy_to_clipboard(text)
        self.notify(f"Copiado: {short(text)}")
