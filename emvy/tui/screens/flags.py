"""Panel de búsqueda de flags/patrones sobre la última captura."""

from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, RichLog

from ...core.search import search_flags, search_regex


class FlagsScreen(Vertical):
    def compose(self):
        yield Label("Búsqueda de flags", classes="title")
        with Horizontal(classes="row"):
            yield Input(
                value=r"flag\{[^}]+\}", placeholder="patrón regex", id="flag_pat"
            )
            yield Button("Buscar patrón", id="flag_search", variant="success")
            yield Button("Patrones por defecto", id="flag_default", variant="primary")
        yield RichLog(id="flag_log", markup=True, wrap=True)

    def _dump(self):
        dump = getattr(self.app, "last_dump", None)
        if dump is None:
            self.query_one("#flag_log", RichLog).write(
                "[yellow]No hay captura. Ve a Explorador → 'Capturar tarjeta' primero.[/]"
            )
        return dump

    @on(Button.Pressed, "#flag_search")
    def _search(self):
        dump = self._dump()
        if dump is None:
            return
        pat = self.query_one("#flag_pat", Input).value or r"flag\{[^}]+\}"
        self._render_hits(search_regex(dump.all_blobs(), pat))

    @on(Button.Pressed, "#flag_default")
    def _default(self):
        dump = self._dump()
        if dump is None:
            return
        self._render_hits(search_flags(dump.all_blobs()))

    def _render_hits(self, hits):
        log = self.query_one("#flag_log", RichLog)
        if not hits:
            log.write("[yellow]Sin coincidencias.[/]")
            return
        log.write(f"[b green]╔══ {len(hits)} posible(s) flag(s) ══╗[/]")
        for h in hits:
            log.write(f"  [b green]{h.match}[/]")
            log.write(f"    [dim]en[/] {h.source}  [dim]({h.where})[/]")
            log.write(f"    [dim]ctx:[/] …{h.context}…")
