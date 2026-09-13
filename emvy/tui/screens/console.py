"""Panel consola: envía APDUs crudos y muestra en vivo el intercambio con el
lector conectado, en dos niveles:

  * **APDU** (`live_log`/`log_response`): el comando parseado con su status word
    — lo que consume `core.emv`. Lo emiten todos los lectores.
  * **Transporte** (`wire_log`): la línea cruda por debajo del APDU — hoy las
    líneas serie del BomberCat (`PING`, `WAIT`, `READY:`, `APDU:<hex>`,
    `RESP:<hex>`, `# debug`). Sirve para ver literalmente qué se manda y qué
    responde el hardware (handshake, detección de tarjeta, framing).

Vive embebido en el Explorador (dentro de un `Collapsible`, que ya aporta su
propio título) para tener a la vista, mientras se captura, ambos niveles."""
from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, RichLog

from ...core import tlv
from ...core.hexutil import to_hex


class ConsoleScreen(Vertical):
    def compose(self):
        with Horizontal(classes="row"):
            yield Input(placeholder="APDU hex (p.ej. 00A404000E325041592E5359532E4444463031)", id="con_apdu")
            yield Button("Enviar", id="con_send", variant="success")
            yield Button("Ver traza", id="con_trace")
            yield Button("Limpiar", id="con_clear")
        yield RichLog(id="con_log", markup=True, highlight=False, wrap=True, max_lines=1000)

    @on(Button.Pressed, "#con_send")
    @on(Input.Submitted, "#con_apdu")
    def _send(self):
        hexstr = self.query_one("#con_apdu", Input).value.strip()
        if not hexstr:
            return
        self.app.send_apdu_ui(hexstr)

    @on(Button.Pressed, "#con_trace")
    def _trace(self):
        log = self.query_one("#con_log", RichLog)
        reader = getattr(self.app, "reader", None)
        if not reader or not reader.trace:
            log.write("[yellow]Sin traza (conecta un lector y envía algo).[/]")
            return
        log.write("[b]── traza ──[/]")
        for e in reader.trace[-40:]:
            log.write(f"[dim]>> {e.command}[/]")
            log.write(f"[dim]<< {e.response}  [{e.sw}][/]")

    @on(Button.Pressed, "#con_clear")
    def _clear(self):
        self.query_one("#con_log", RichLog).clear()

    # -- traza en vivo: la app la retransmite aquí en cada intercambio del
    # lector conectado (capturas, PoCs, escritura...), no solo lo enviado
    # a mano desde esta pantalla — así se ve exactamente qué pasa (o qué se
    # está perdiendo) mientras corre cualquier otra pestaña.
    def live_log(self, e) -> None:
        log = self.query_one("#con_log", RichLog)
        color = "green" if e.sw == "9000" else "red"
        log.write(f"[dim]›[/] [cyan]>>[/] {e.command}")
        log.write(f"[dim]›[/] [{color}]<<[/] {e.response or '(vacío)'}  [{color}][{e.sw}][/]")

    # -- transporte en vivo: línea serie cruda (BomberCat) por debajo del APDU.
    # Se muestra con un estilo distinto (etiqueta ⇢/⇠ + transporte tenue) para
    # separarlo visualmente de la traza APDU parseada de arriba.
    def wire_log(self, e) -> None:
        log = self.query_one("#con_log", RichLog)
        tag = f"[dim]{e.transport or 'wire'}[/]"
        if e.direction == "tx":
            log.write(f"{tag} [magenta]⇢[/] {e.text}")
        elif e.direction == "rx":
            err = e.text.startswith("ERR") or "NOCARD" in e.text
            col = "yellow" if err else "blue"
            log.write(f"{tag} [{col}]⇠[/] [{col}]{e.text}[/]")
        else:
            log.write(f"{tag} [dim]· {e.text}[/]")

    # -- separador con contexto (conexión/desconexión de lector) -----------
    def banner(self, text: str) -> None:
        self.query_one("#con_log", RichLog).write(f"[b]── {text} ──[/]")

    # -- llamado por la app tras enviar ------------------------------------
    def log_response(self, hexstr, resp):
        log = self.query_one("#con_log", RichLog)
        log.write(f"[cyan]>>[/] {hexstr.upper()}")
        color = "green" if resp.ok else "red"
        log.write(f"[{color}]<<[/] {to_hex(resp.data, sep=' ') or '(vacío)'}  "
                  f"[{color}][{resp.sw_hex}][/] {resp.sw_str()}")
        if resp.data:
            parsed = tlv.parse(resp.data)
            if parsed:
                for line in parsed.dump().splitlines():
                    log.write(f"   {line}")
