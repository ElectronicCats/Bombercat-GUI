"""Panel Intercept ("Burp para EMV"): edita reglas, actívalas y observa en vivo
los APDUs (comando/respuesta) que pasan por el interceptor, con las
modificaciones aplicadas. Al activarse, TODO el tráfico de la sesión (Consola,
Explorador, PoC en vivo) pasa por estas reglas."""
from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Label, RichLog, TextArea

from ...core import intercept
from ...core.hexutil import to_hex

_DEFAULT_RULES = """\
# Reglas del interceptor (una por línea; '#' = comentario). Ejemplos:
# resp set-tag 82 3900          # reescribe el AIP en las respuestas
# resp set-sw 9000 @A8          # fuerza SW=9000 solo en GPO (INS A8)
# cmd  set-tag 9F02 000000000100
# resp replace 9F34031F0302 9F34035E0300
"""


class InterceptScreen(Vertical):
    def compose(self):
        yield Label("Intercept — MITM de APDUs", classes="title")
        with Horizontal(classes="row"):
            yield Checkbox("Interceptor activo", id="ic_active")
            yield Button("Aplicar reglas", id="ic_apply", variant="success")
            yield Button("Limpiar log", id="ic_clear")
        yield Label("", id="ic_status", classes="hint")
        yield self._editor()
        yield RichLog(id="ic_log", markup=True, wrap=True)

    @staticmethod
    def _editor():
        try:
            return TextArea.code_editor(_DEFAULT_RULES, id="ic_rules")
        except Exception:
            return TextArea(_DEFAULT_RULES, id="ic_rules")

    def on_mount(self):
        self._apply()

    @on(Button.Pressed, "#ic_apply")
    def _apply_btn(self):
        self._apply()

    def _apply(self):
        text = self.query_one("#ic_rules", TextArea).text
        rules, errors = intercept.parse_rules(text)
        self.app.intercept_rules = rules
        st = f"{len(rules)} regla(s) cargada(s)"
        if errors:
            st += f"   [red]({len(errors)} error(es): {errors[0]})[/]"
        self.query_one("#ic_status", Label).update(st)

    @on(Checkbox.Changed, "#ic_active")
    def _toggle(self, event):
        self.app.intercept_active = bool(event.value)
        self.app.notify("Interceptor " + ("ACTIVO" if event.value else "inactivo"),
                        severity=("warning" if event.value else "information"))

    @on(Button.Pressed, "#ic_clear")
    def _clear(self):
        self.query_one("#ic_log", RichLog).clear()

    def log_exchange(self, ex) -> None:
        log = self.query_one("#ic_log", RichLog)
        cmd = to_hex(ex.cmd_after.to_bytes(), sep=" ")
        data = to_hex(ex.resp_after.data, sep=" ")
        tag = " [yellow](modificado)[/]" if ex.modified else ""
        log.write(f"[cyan]>>[/] {cmd}{tag}")
        log.write(f"[green]<<[/] [{ex.resp_after.sw_hex}] {data or '(vacío)'}")
        for n in ex.notes:
            log.write(f"   [yellow]· {n}[/]")
