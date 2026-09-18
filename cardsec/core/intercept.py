"""Interceptor de APDUs ("Burp para EMV"): motor puro de reglas que reescribe
comandos/respuestas al vuelo y registra cada intercambio.

Un interceptor es un **middleware de `Transceiver`**: envuelve un `send` upstream
(hacia la tarjeta real), aplica reglas al comando, lo envía, aplica reglas a la
respuesta, emite un evento y devuelve la respuesta (posiblemente modificada).
Todo el motor es puro; el transporte lo aporta el `send` que se envuelve.

DSL de reglas (una por línea, `#` = comentario):
    cmd  set-tag <TAG> <HEX>      # en los datos del comando (TLV), fija el tag
    resp set-tag <TAG> <HEX>      # en los datos de la respuesta (TLV)
    resp set-sw  <SW4HEX>         # sobrescribe el status word (p.ej. 9000)
    cmd  replace <FROMHEX> <TOHEX># sustitución de bytes cruda en los datos
    resp replace <FROMHEX> <TOHEX>
Sufijo opcional `@<INSHEX>` para aplicar solo a cierto INS (p.ej. `@B2`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import tlv
from .apdu import APDU, Response
from .hexutil import from_hex, to_hex


# ---------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    scope: str  # "cmd" | "resp"
    action: str  # "set-tag" | "set-sw" | "replace"
    args: tuple  # bytes/strings ya normalizados
    when_ins: int | None = None
    raw: str = ""


def parse_rules(text: str) -> tuple[list[Rule], list[str]]:
    """Parsea el DSL. Devuelve (reglas, errores)."""
    rules: list[Rule] = []
    errors: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        when_ins = None
        toks = []
        for t in s.split():
            if t.startswith("@"):
                try:
                    when_ins = int(t[1:], 16)
                except ValueError:
                    errors.append(f"L{lineno}: INS inválido en {t!r}")
            else:
                toks.append(t)
        if len(toks) < 2:
            errors.append(f"L{lineno}: regla incompleta: {line!r}")
            continue
        scope, action = toks[0].lower(), toks[1].lower()
        if scope not in ("cmd", "resp"):
            errors.append(f"L{lineno}: scope debe ser cmd|resp: {line!r}")
            continue
        try:
            rule = _build_rule(scope, action, toks[2:], when_ins, line)
        except ValueError as e:
            errors.append(f"L{lineno}: {e}")
            continue
        rules.append(rule)
    return rules, errors


def _build_rule(scope, action, args, when_ins, raw) -> Rule:
    if action == "set-tag":
        if len(args) != 2:
            raise ValueError("set-tag requiere <TAG> <HEX>")
        tag = args[0].upper()
        val = from_hex(args[1])
        return Rule(scope, "set-tag", (tag, val), when_ins, raw)
    if action == "set-sw":
        if scope != "resp" or len(args) != 1:
            raise ValueError("set-sw es 'resp set-sw <SW4HEX>'")
        sw = from_hex(args[0])
        if len(sw) != 2:
            raise ValueError("el SW debe ser 2 bytes (p.ej. 9000)")
        return Rule(scope, "set-sw", (sw[0], sw[1]), when_ins, raw)
    if action == "replace":
        if len(args) != 2:
            raise ValueError("replace requiere <FROMHEX> <TOHEX>")
        return Rule(
            scope, "replace", (from_hex(args[0]), from_hex(args[1])), when_ins, raw
        )
    raise ValueError(f"acción desconocida: {action}")


# ---------------------------------------------------------------------------
# Aplicación de reglas
# ---------------------------------------------------------------------------
def _replace_tag(tlvs, tag: str, new_value: bytes) -> tuple[tlv.TLVList, bool]:
    out = tlv.TLVList()
    changed = False
    for t in tlvs:
        if t.constructed and t.children:
            ch, c2 = _replace_tag(t.children, tag, new_value)
            out.append(tlv.TLV(t.tag, b"", list(ch), constructed=True))
            changed = changed or c2
        elif t.tag == tag:
            out.append(tlv.tlv(t.tag, new_value))
            changed = True
        else:
            out.append(t)
    return out, changed


def set_tag_in(data: bytes, tag: str, new_value: bytes) -> tuple[bytes, bool]:
    """Reemplaza el valor del `tag` dentro de `data` (interpretado como TLV)."""
    try:
        parsed = tlv.parse(data)
    except Exception:
        return data, False
    out, changed = _replace_tag(parsed, tag.upper(), new_value)
    return (tlv.encode(out), True) if changed else (data, False)


def apply_command(apdu: APDU, rules: list[Rule]) -> tuple[APDU, list[str]]:
    data = apdu.data
    notes: list[str] = []
    for r in rules:
        if r.scope != "cmd" or (r.when_ins is not None and r.when_ins != apdu.ins):
            continue
        if r.action == "set-tag":
            tag, val = r.args
            data, ok = set_tag_in(data, tag, val)
            if ok:
                notes.append(f"cmd set-tag {tag}={to_hex(val)}")
        elif r.action == "replace":
            frm, to = r.args
            if frm in data:
                data = data.replace(frm, to)
                notes.append(f"cmd replace {to_hex(frm)}→{to_hex(to)}")
    return (replace(apdu, data=data) if data != apdu.data else apdu), notes


def apply_response(
    resp: Response, rules: list[Rule], ins: int | None = None
) -> tuple[Response, list[str]]:
    data, sw1, sw2 = resp.data, resp.sw1, resp.sw2
    notes: list[str] = []
    for r in rules:
        if r.scope != "resp" or (r.when_ins is not None and r.when_ins != ins):
            continue
        if r.action == "set-tag":
            tag, val = r.args
            data, ok = set_tag_in(data, tag, val)
            if ok:
                notes.append(f"resp set-tag {tag}={to_hex(val)}")
        elif r.action == "set-sw":
            sw1, sw2 = r.args
            notes.append(f"resp set-sw {sw1:02X}{sw2:02X}")
        elif r.action == "replace":
            frm, to = r.args
            if frm in data:
                data = data.replace(frm, to)
                notes.append(f"resp replace {to_hex(frm)}→{to_hex(to)}")
    changed = data != resp.data or sw1 != resp.sw1 or sw2 != resp.sw2
    return (Response(data, sw1, sw2) if changed else resp), notes


# ---------------------------------------------------------------------------
# Middleware de Transceiver
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Exchange:
    cmd_before: APDU
    cmd_after: APDU
    resp_before: Response
    resp_after: Response
    notes: list[str] = field(default_factory=list)

    @property
    def modified(self) -> bool:
        return bool(self.notes)


def to_apdu(command) -> APDU:
    """Normaliza un comando (APDU o bytes) a APDU."""
    if isinstance(command, APDU):
        return command
    b = bytes(command)
    if len(b) < 4:
        raise ValueError("APDU demasiado corto")
    cla, ins, p1, p2 = b[0], b[1], b[2], b[3]
    rest = b[4:]
    data, le = b"", None
    if len(rest) == 1:
        le = rest[0]
    elif len(rest) >= 2:
        lc = rest[0]
        data = rest[1 : 1 + lc]
        after = rest[1 + lc :]
        le = after[0] if after else None
    return APDU(cla, ins, p1, p2, data, le)


def intercepting(send, rules: list[Rule], on_event=None):
    """Envuelve un `Transceiver` con el interceptor: aplica reglas al comando y a
    la respuesta, emite un `Exchange` por cada intercambio, y devuelve la
    respuesta (posiblemente modificada)."""

    def transceiver(command) -> Response:
        cmd_before = to_apdu(command)
        cmd_after, cnotes = apply_command(cmd_before, rules)
        resp_before = send(cmd_after)
        resp_after, rnotes = apply_response(resp_before, rules, cmd_after.ins)
        if on_event:
            on_event(
                Exchange(
                    cmd_before, cmd_after, resp_before, resp_after, cnotes + rnotes
                )
            )
        return resp_after

    return transceiver
