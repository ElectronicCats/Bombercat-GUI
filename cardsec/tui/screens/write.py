"""Pestaña 'Escritura': modo de escritura en tarjetas ISO 7816 / EMV.

UPDATE RECORD, UPDATE BINARY, PUT DATA, APPEND RECORD. **Modifica la tarjeta**;
solo tarjetas propias/de laboratorio. Muchas escrituras requieren canal
seguro/autenticación (la tarjeta responde SW 6982/6985).
"""

from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, RichLog, Select

from ...core import cardwrite
from ...core.hexutil import from_hex, to_hex

_OPS = [
    ("UPDATE RECORD", "record"),
    ("UPDATE BINARY", "binary"),
    ("PUT DATA", "data"),
    ("APPEND RECORD", "append"),
]


class WriteScreen(Vertical):
    def compose(self):
        yield Label("Escritura en tarjeta", classes="title")
        yield Label(
            "[yellow]⚠ Modifica la tarjeta (puede ser irreversible). Solo tarjetas "
            "propias/de laboratorio; muchas escrituras exigen canal seguro.[/]",
            classes="hint",
        )
        with Horizontal(classes="row"):
            yield Select(_OPS, value="record", allow_blank=False, id="w_op")
            yield Input(placeholder="SFI", id="w_sfi")
            yield Input(placeholder="registro / offset", id="w_num")
            yield Input(placeholder="tag (PUT DATA)", id="w_tag")
        with Horizontal(classes="row"):
            yield Input(placeholder="datos en hex", id="w_data")
            yield Button("Escribir", id="w_write", variant="error")
        yield RichLog(id="w_log", markup=True, wrap=True)

    @on(Button.Pressed, "#w_write")
    def _write(self):
        op = self.query_one("#w_op", Select).value
        try:
            data = from_hex(self.query_one("#w_data", Input).value.strip())
        except ValueError:
            self.app.notify("Datos hex inválidos.", severity="error")
            return
        params = {"data": data}
        try:
            if op == "record":
                params["sfi"] = int(self.query_one("#w_sfi", Input).value)
                params["record"] = int(self.query_one("#w_num", Input).value)
            elif op == "binary":
                params["offset"] = int(self.query_one("#w_num", Input).value or "0")
                sfi = self.query_one("#w_sfi", Input).value.strip()
                params["sfi"] = int(sfi) if sfi else None
            elif op == "data":
                params["tag"] = int(self.query_one("#w_tag", Input).value.strip(), 16)
            elif op == "append":
                params["sfi"] = int(self.query_one("#w_sfi", Input).value)
        except ValueError:
            self.app.notify("SFI/registro/offset/tag inválido.", severity="warning")
            return
        self.query_one("#w_log", RichLog).write(f"[dim]→ {op} {to_hex(data)}…[/]")
        self.app.write_card_ui(op, params)

    def log_write(self, op: str, resp) -> None:
        log = self.query_one("#w_log", RichLog)
        ok = resp.sw == 0x9000
        log.write(
            f"[b {'green' if ok else 'red'}]{op}  SW {resp.sw_hex}[/] "
            f"{cardwrite.write_status(resp.sw)}"
        )
        if resp.data:
            log.write(f"   data: {to_hex(resp.data)}")
