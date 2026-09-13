"""Panel ISO 8583: constructor de mensajes (MTI + campos), traducción legible y
envío por TCP a un host de laboratorio (switch/adquirente). El envío corre en un
hilo de trabajo; la respuesta se parsea y traduce."""
from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, RichLog, Select

from ...core.hexutil import from_hex, to_hex
from ...payments import iso8583
from ..widgets.copyable import CopyableDataTable


class Iso8583Screen(Vertical):
    def compose(self):
        yield Label("ISO 8583 — constructor + envío", classes="title")
        with Horizontal(classes="row"):
            yield Input(value="0200", id="iso_mti", placeholder="MTI")
            yield Input(placeholder="DE (nº)", id="iso_de")
            yield Input(placeholder="valor (hex o texto)", id="iso_val")
            yield Checkbox("hex", value=True, id="iso_hex")
            yield Button("Set campo", id="iso_set", variant="primary")
            yield Button("Quitar sel.", id="iso_del", variant="error")
        yield CopyableDataTable(id="iso_fields")
        with Horizontal(classes="row"):
            yield Button("Construir", id="iso_build", variant="success")
            yield Input(value="127.0.0.1", id="iso_host", placeholder="host")
            yield Input(value="0", id="iso_port", placeholder="puerto")
            yield Select([("hdr 2B", "2"), ("sin hdr", "0"), ("hdr 4B", "4")],
                         value="2", allow_blank=False, id="iso_hdr")
            yield Button("Enviar", id="iso_send", variant="warning")
        yield RichLog(id="iso_log", markup=True, wrap=True)

    def on_mount(self):
        t = self.query_one("#iso_fields", DataTable)
        t.add_columns("DE", "nombre", "valor (hex)")
        t.cursor_type = "row"
        self._fields: dict[int, bytes] = {}
        self._built: bytes | None = None
        self._des: list[int] = []

    def _refresh(self):
        t = self.query_one("#iso_fields", DataTable)
        t.clear()
        self._des = []
        for de in sorted(self._fields):
            spec = iso8583.DEFAULT_SPEC.get(de)
            t.add_row(str(de), spec.name if spec else "?", to_hex(self._fields[de]))
            self._des.append(de)

    @on(Button.Pressed, "#iso_set")
    def _set(self):
        try:
            de = int(self.query_one("#iso_de", Input).value)
        except ValueError:
            self.app.notify("Número de DE inválido.", severity="warning")
            return
        raw = self.query_one("#iso_val", Input).value.strip()
        try:
            val = (from_hex(raw) if self.query_one("#iso_hex", Checkbox).value
                   else raw.encode("latin-1"))
        except ValueError:
            self.app.notify("Valor hex inválido.", severity="error")
            return
        self._fields[de] = val
        self.query_one("#iso_de", Input).value = ""
        self.query_one("#iso_val", Input).value = ""
        self._refresh()

    @on(Button.Pressed, "#iso_del")
    def _del(self):
        if not self._des:
            return
        idx = self.query_one("#iso_fields", DataTable).cursor_row or 0
        if 0 <= idx < len(self._des):
            self._fields.pop(self._des[idx], None)
            self._refresh()

    @on(Button.Pressed, "#iso_build")
    def _build(self):
        try:
            msg = iso8583.build(self.query_one("#iso_mti", Input).value.strip(), self._fields)
        except Exception as e:
            self.app.notify(f"No se pudo construir: {e}", severity="error")
            return
        self._built = msg
        log = self.query_one("#iso_log", RichLog)
        log.write("[b]Construido:[/] " + to_hex(msg))
        log.write(iso8583.translate(msg).text())

    @on(Button.Pressed, "#iso_send")
    def _send(self):
        if not self._built:
            self.app.notify("Construye el mensaje primero.", severity="warning")
            return
        host = self.query_one("#iso_host", Input).value.strip()
        port = self.query_one("#iso_port", Input).value.strip()
        hdr = self.query_one("#iso_hdr", Select).value
        if not port.isdigit() or int(port) == 0:
            self.app.notify("Indica un puerto válido.", severity="warning")
            return
        self.query_one("#iso_log", RichLog).write(
            f"[dim]→ enviando a {host}:{port} (header {hdr}B)…[/]")
        self.app.send_iso8583_ui(host, port, self._built, hdr)

    def show_response(self, resp: bytes) -> None:
        log = self.query_one("#iso_log", RichLog)
        log.write("[b green]Respuesta:[/] " + (to_hex(resp) or "(vacía)"))
        if resp:
            try:
                log.write(iso8583.translate(resp).text())
            except Exception as e:
                log.write(f"[red]no parseable como ISO 8583: {e}[/]")
