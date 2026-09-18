"""Widgets y helpers comunes de la TUI."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Barra de estado: proyecto activo, lector conectado y estado de tarjeta."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    def show(self, project: str | None, reader: str | None, card: str | None) -> None:
        proj = f"[b]proyecto[/] {project or '—'}"
        rdr = f"[b]lector[/] {reader or '—'}"
        crd = f"[b]tarjeta[/] {card or '—'}"
        self.update(f"{proj}   │   {rdr}   │   {crd}")
