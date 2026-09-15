"""Plantillas de PoCs **genéricos** para cualquier proyecto/switch.

Cada plantilla es un plugin `@poc` que lee la configuración del switch y del
terminal desde variables del proyecto (`ctx.var`), así que el mismo PoC sirve para
todos los engagements: solo cambias las variables (switch_host, switch_port, TID,
MID, MCC, TPDU, TLS…). Se materializan en `<proyecto>/pocs/` con
`emvy poc new <id> --template <nombre>`.

Variables reconocidas (todas opcionales salvo destino):
  switch_host, switch_port, switch_tls(0/1), tpdu(hex), switch_header_len,
  terminal_id/tid, merchant_id/mid, mcc, currency(hex), country(hex),
  pos_entry, ttq, cvm_results, amount(centavos)
"""

from __future__ import annotations

_SIGNON = '''\
"""PoC genérico: sign-on de red 0800/0810 (verifica conectividad al switch).
Configura: switch_host, switch_port, switch_tls, tpdu. Autorización: documenta el alcance.
"""
from emvy.poc import poc, Severity, Status
from emvy.payments import SwitchConfig, switch


@poc(id="{id}", title="Switch sign-on 0800", category="switch",
     severity=Severity.INFO, authorization="Prueba autorizada — <cliente/alcance>.")
def run(ctx):
    cfg = SwitchConfig.from_vars(ctx.var)
    ctx.log(f"sign-on a {{cfg.host}}:{{cfg.port}} (TLS={{cfg.tls}})")
    if ctx.dry_run or not cfg.port:
        return ctx.result(Status.INFO, "dry-run / sin destino: no se envió 0800")
    res = switch.run_signon(cfg)
    ctx.save_evidence("signon.txt", res.summary())
    ok = bool(res.response)
    return ctx.result(Status.INFO if ok else Status.ERROR,
                      f"0810 {{'recibido' if ok else 'sin respuesta'}} ({{len(res.response)}}B)")
'''

_PURCHASE = '''\
"""PoC genérico: autorización EMV 0200→0210 con F55/ARQC real de la tarjeta.
Requiere --card (EmvCard) y las variables del switch/terminal. Respeta --dry-run.
Autorización: prueba controlada con tarjeta propia/de laboratorio.
"""
from emvy.poc import poc, Severity, Status
from emvy.payments import SwitchConfig, switch


@poc(id="{id}", title="Autorización EMV 0200 (switch)", category="switch",
     severity=Severity.HIGH, authorization="Prueba autorizada — <cliente/alcance>.")
def run(ctx):
    if ctx.card is None:
        return ctx.result(Status.SKIPPED, "falta la tarjeta: usa --card o el lector en vivo")
    cfg = SwitchConfig.from_vars(ctx.var)
    amount = int(ctx.var("amount") or 500)
    ctx.log(f"0200 a {{cfg.host}}:{{cfg.port}} monto={{amount}} (dry_run={{ctx.dry_run}})")

    res = switch.run_purchase(cfg, ctx.card, amount, dry_run=ctx.dry_run)
    ctx.save_evidence("auth.txt", res.summary())
    if ctx.dry_run or not res.response:
        return ctx.result(Status.INFO, "mensaje 0200 construido (no enviado)")

    status = Status.VULNERABLE if res.approved else Status.INFO
    finding = None
    if res.approved:
        finding = ctx.finding("Autorización aprobada sin CVM", Severity.HIGH,
                              f"F39={{res.rc}} {{res.rc_meaning}}")
    return ctx.result(status, f"F39={{res.rc}} {{res.rc_meaning}}",
                      [finding] if finding else [])
'''

_REVERSAL = '''\
"""PoC genérico: reverso 0400→0410 referenciando una transacción previa.
Config: switch_* + variables 'rrn' y 'stan' (o pásalas con --var). Respeta --dry-run.
"""
from emvy.poc import poc, Severity, Status
from emvy.payments import SwitchConfig, switch


@poc(id="{id}", title="Reverso 0400 (switch)", category="switch",
     severity=Severity.MEDIUM, authorization="Prueba autorizada — <cliente/alcance>.")
def run(ctx):
    cfg = SwitchConfig.from_vars(ctx.var)
    amount = int(ctx.var("amount") or 500)
    rrn = ctx.var("rrn") or ""
    stan = ctx.var("stan") or "000001"
    msg = switch.build_reversal(cfg, stan=stan, rrn=rrn, amount_cents=amount)
    ctx.save_evidence("reversal_0400.hex", msg.hex())
    if ctx.dry_run or not cfg.port:
        return ctx.result(Status.INFO, "0400 construido (dry-run / sin destino)")
    sock = switch._connect(cfg)
    try:
        switch.exchange(cfg, sock, switch.iso8583.build_network_0800())
        resp = switch.exchange(cfg, sock, msg)
    finally:
        sock.close()
    _, fields, rc = switch._parse_and_rc(resp)
    ctx.save_evidence("reversal_0410.hex", resp.hex())
    return ctx.result(Status.INFO, f"0410 F39={{rc}} {{switch.iso8583.response_meaning(rc)}}")
'''

TEMPLATES: dict[str, str] = {
    "iso8583-signon": _SIGNON,
    "iso8583-purchase": _PURCHASE,
    "iso8583-reversal": _REVERSAL,
}


def list_templates() -> list[str]:
    return sorted(TEMPLATES)


def render(name: str, poc_id: str) -> str:
    if name not in TEMPLATES:
        raise KeyError(
            f"plantilla desconocida: {name!r}. Disponibles: {', '.join(list_templates())}"
        )
    return TEMPLATES[name].format(id=poc_id)
