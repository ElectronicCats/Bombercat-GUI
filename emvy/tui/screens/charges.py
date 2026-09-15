"""Pestaña 'Cobros': flujo de pago end-to-end contra un switch/adquirente.

Crear un cobro (monto + tarjeta) → sign-on 0800 → autorización 0200 → seguir la
respuesta 0210 (F39) → reverso 0400 opcional. El switch y el terminal se
configuran por **variables del proyecto** (switch_host, switch_port, switch_tls,
tpdu, terminal_id, merchant_id, mcc…). Genérico: apunta al switch que quieras.
"""

from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Input, Label, RichLog, Select

from ...payments import SwitchConfig
from ...project import store

_CARD_SOURCES = [
    ("Sesión (última captura)", "session"),
    ("Captura guardada", "saved"),
    ("Lector en vivo", "live"),
]


class ChargesScreen(Vertical):
    def compose(self):
        yield Label(
            "Cobros — flujo de switch (crear → enviar → respuesta)", classes="title"
        )
        yield Label("", id="ch_cfg", classes="hint")
        with Horizontal(classes="row"):
            yield Input(value="500", id="ch_amount", placeholder="monto (centavos)")
            yield Select(_CARD_SOURCES, value="session", allow_blank=False, id="ch_src")
            yield Select(
                [], prompt="captura guardada…", allow_blank=True, id="ch_capfile"
            )
            yield Checkbox("sign-on", value=True, id="ch_signon")
            yield Checkbox("dry-run", value=True, id="ch_dry")
        with Horizontal(classes="row"):
            yield Button("Sign-on 0800", id="ch_signon_btn")
            yield Button("Crear y enviar 0200", id="ch_purchase", variant="success")
            yield Button("Reverso 0400", id="ch_reversal", variant="warning")
            yield Button("Recargar", id="ch_reload")
        yield RichLog(id="ch_log", markup=True, wrap=True)

    def on_mount(self):
        self.reload()

    def _vars(self) -> dict:
        proj = store.active_project()
        if not proj:
            return {}
        try:
            return {v.name: v.value for v in store.load_project_variables(proj)}
        except Exception:
            return {}

    def reload(self):
        variables = self._vars()
        cfg = SwitchConfig.from_vars(lambda k: variables.get(k))
        proj = store.active_project()
        dest = (
            f"{cfg.host}:{cfg.port}"
            if cfg.port
            else "[red]sin destino (define switch_host/switch_port)[/]"
        )
        self.query_one("#ch_cfg", Label).update(
            f"Destino: [b]{dest}[/]  TLS={cfg.tls}  ·  TID={cfg.tid or '—'} "
            f"MID={cfg.mid or '—'} MCC={cfg.mcc}  ·  proyecto: {proj.name if proj else '—'}"
        )
        caps = [c.name for c in store.list_captures(proj)] if proj else []
        self.query_one("#ch_capfile", Select).set_options([(c, c) for c in caps])

    def _amount(self) -> int:
        try:
            return int(self.query_one("#ch_amount", Input).value or "0")
        except ValueError:
            return 0

    def _opts(self) -> dict:
        src = self.query_one("#ch_src", Select).value
        capfile = self.query_one("#ch_capfile", Select).value
        return {
            "card_source": src,
            "capture_name": (
                capfile if src == "saved" and isinstance(capfile, str) else None
            ),
            "amount": self._amount(),
            "dry_run": self.query_one("#ch_dry", Checkbox).value,
            "sign_on": self.query_one("#ch_signon", Checkbox).value,
        }

    @on(Button.Pressed, "#ch_reload")
    def _reload_btn(self):
        self.reload()

    @on(Button.Pressed, "#ch_signon_btn")
    def _signon(self):
        self.app.run_switch_flow_ui("signon", **self._opts())

    @on(Button.Pressed, "#ch_purchase")
    def _purchase(self):
        self.app.run_switch_flow_ui("purchase", **self._opts())

    @on(Button.Pressed, "#ch_reversal")
    def _reversal(self):
        self.app.run_switch_flow_ui("reversal", **self._opts())

    # -- llamado por la app tras el flujo ----------------------------------
    def log_flow(self, kind: str, res) -> None:
        log = self.query_one("#ch_log", RichLog)
        color = "green" if res.approved else ("yellow" if not res.response else "red")
        log.write(f"[b]── {kind.upper()} ──[/]")
        log.write(f"[cyan]>>[/] {res.mti}: {res.request.hex()}")
        if res.response:
            log.write(f"[green]<<[/] {res.response.hex()}")
            log.write(
                f"[b {color}]F39={res.rc}[/] {res.rc_meaning}  → "
                + ("[green]APROBADA[/]" if res.approved else "[red]DECLINADA/otro[/]")
            )
        for line in res.log:
            log.write(f"   [dim]{line}[/]")
