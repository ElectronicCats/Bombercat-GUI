"""Flujo genérico de switch/adquirente ISO 8583 (efecto en el borde).

Modela, **sin objetivos hardcodeados**, un flujo de switch/adquirente real: sign-on
(0800) → autorización (0200 con F55/ARQC real del chip) → respuesta (0210) →
reverso opcional (0400/0410). Todo parametrizado por `SwitchConfig` (host, puerto,
TLS, TPDU, framing y perfil de terminal), de modo que cada proyecto apunte al suyo.

El transporte (socket/TLS) vive aquí; el armado de mensajes reutiliza el codec
puro `iso8583`. Las particularidades exactas de un switch (p.ej. longitud LLVAR en
binario, tags F55 requeridos) se ajustan por configuración/engagement.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.hexutil import from_hex, to_hex
from . import iso8583
from .emvcard import EmvCard


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on", "si", "sí")


@dataclass(frozen=True)
class SwitchConfig:
    # --- destino / transporte ---
    host: str = "127.0.0.1"
    port: int = 0
    tls: bool = False
    verify_tls: bool = False
    tpdu: bytes = b""  # prefijo TPDU (p.ej. 6000000000), o vacío
    header_len: int = 2  # bytes del prefijo de longitud (0 = sin prefijo)
    timeout: float = 20.0
    keylog: str = ""  # ruta TLS keylog (Wireshark), opcional
    # --- perfil de terminal (campos ISO/EMV) ---
    tid: str = ""  # F41 (8)
    mid: str = ""  # F42 (15)
    mcc: str = "5999"  # F18
    currency: str = "0484"  # F49 / 5F2A (hex)
    country: str = "0484"  # 9F1A (hex)
    term_type: str = "22"  # 9F35
    ttq: str = "26000000"  # 9F66
    cvm_results: str = "1F0002"  # 9F34
    pos_entry: str = "0710"  # F22 (contactless EMV)

    @classmethod
    def from_vars(cls, get) -> "SwitchConfig":
        """Construye la config leyendo variables del proyecto con `get(name)`
        (p.ej. `ctx.var`). Reconoce alias comunes (terminal_id/tid, etc.)."""

        def g(name, default=""):
            for k in (name if isinstance(name, tuple) else (name,)):
                v = get(k)
                if v not in (None, ""):
                    return v
            return default

        return cls(
            host=g("switch_host", "127.0.0.1"),
            port=int(g("switch_port", "0") or 0),
            tls=_truthy(g("switch_tls", "0")),
            verify_tls=_truthy(g("switch_verify_tls", "0")),
            tpdu=from_hex(g("tpdu", "") or ""),
            header_len=int(g("switch_header_len", "2") or 2),
            tid=g(("terminal_id", "tid"), ""),
            mid=g(("merchant_id", "mid"), ""),
            mcc=g("mcc", "5999"),
            currency=g("currency", "0484"),
            country=g("country", "0484"),
            term_type=g("term_type", "22"),
            ttq=g("ttq", "26000000"),
            cvm_results=g("cvm_results", "1F0002"),
            pos_entry=g("pos_entry", "0710"),
        )


@dataclass
class FlowResult:
    request: bytes
    response: bytes = b""
    mti: str = ""
    fields: dict = field(default_factory=dict)
    rc: str | None = None
    rc_meaning: str = ""
    approved: bool = False
    log: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"request  {self.mti or '0200'}: {to_hex(self.request)}"]
        if self.response:
            lines.append(f"response {self.mti}: {to_hex(self.response)}")
            lines.append(
                f"F39={self.rc}  {self.rc_meaning}  → "
                + ("APROBADA" if self.approved else "DECLINADA/otro")
            )
        lines.extend(self.log)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Armado de mensajes (reutiliza el codec iso8583)
# ---------------------------------------------------------------------------
def build_purchase(cfg: SwitchConfig, card: EmvCard, amount_cents: int) -> bytes:
    """0200 de compra con F55 (ICC/ARQC) desde un EmvCard, según la config."""
    now = datetime.now(timezone.utc)
    stan = str(now.microsecond % 1000000).zfill(6)
    txn_date = card.txn_date or now.strftime("%y%m%d")  # YYMMDD
    mmdd = txn_date[2:6]
    pan = card.pan_digits or ""
    track2 = card.track2 or ""
    expiry = (card.expiry or "")[:4]

    terminal = {
        "country": cfg.country,
        "currency": cfg.currency,
        "txn_type": "00",
        "cvm_results": cfg.cvm_results,
        "term_type": cfg.term_type,
        "ttq": cfg.ttq,
    }
    f55 = iso8583.emv_icc(card, amount_cents=amount_cents, terminal=terminal)

    fields = {
        2: iso8583.bcd(pan),
        3: from_hex("000000"),
        4: iso8583.bcd_amount(amount_cents),
        11: iso8583.bcd(stan[:6]),
        12: iso8583.bcd(now.strftime("%H%M%S")),
        13: iso8583.bcd(mmdd),  # = 9A en F55
        14: iso8583.bcd(expiry),
        18: iso8583.bcd(cfg.mcc),
        22: from_hex(cfg.pos_entry),
        25: from_hex("00"),
        35: iso8583.bcd(track2) if track2 else b"",
        37: (mmdd + stan.zfill(8)[:8]).ljust(12, "0")[:12].encode("ascii"),  # RRN (12)
        41: (cfg.tid or "").ljust(8)[:8].encode("ascii"),
        42: (cfg.mid or "").ljust(15)[:15].encode("ascii"),
        49: from_hex(cfg.currency),
        55: f55,
    }
    fields = {k: v for k, v in fields.items() if v}  # descarta vacíos
    return iso8583.build("0200", fields)


def build_reversal(
    cfg: SwitchConfig, *, stan: str, rrn: str, amount_cents: int, pan: str = ""
) -> bytes:
    """0400 de reverso referenciando una transacción previa (sin F35/F55)."""
    fields = {
        3: from_hex("000000"),
        4: iso8583.bcd_amount(amount_cents),
        11: iso8583.bcd(stan.zfill(6)[:6]),
        37: rrn.ljust(12)[:12].encode("ascii"),
        41: (cfg.tid or "").ljust(8)[:8].encode("ascii"),
        42: (cfg.mid or "").ljust(15)[:15].encode("ascii"),
        49: from_hex(cfg.currency),
    }
    if pan:
        fields[2] = iso8583.bcd(pan)
    return iso8583.build("0400", fields)


# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------
def _connect(cfg: SwitchConfig):
    raw = socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout)
    if not cfg.tls:
        raw.settimeout(cfg.timeout)
        return raw
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = bool(cfg.verify_tls)
    ctx.verify_mode = ssl.CERT_REQUIRED if cfg.verify_tls else ssl.CERT_NONE
    if cfg.keylog and hasattr(ctx, "keylog_filename"):
        ctx.keylog_filename = cfg.keylog
    tls = ctx.wrap_socket(raw, server_hostname=cfg.host)
    tls.settimeout(cfg.timeout)
    return tls


def _frame(cfg: SwitchConfig, payload: bytes) -> bytes:
    body = cfg.tpdu + payload
    if cfg.header_len <= 0:
        return body
    return len(body).to_bytes(cfg.header_len, "big") + body


def _recv_n(sock, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _recv(cfg: SwitchConfig, sock) -> bytes:
    if cfg.header_len <= 0:
        data = sock.recv(65535)
    else:
        hdr = _recv_n(sock, cfg.header_len)
        if len(hdr) < cfg.header_len:
            return b""
        data = _recv_n(sock, int.from_bytes(hdr, "big"))
    return (
        data[len(cfg.tpdu) :]
        if cfg.tpdu and data[: len(cfg.tpdu)] == cfg.tpdu
        else data
    )


def exchange(cfg: SwitchConfig, sock, payload: bytes) -> bytes:
    sock.sendall(_frame(cfg, payload))
    return _recv(cfg, sock)


# ---------------------------------------------------------------------------
# Flujos completos
# ---------------------------------------------------------------------------
def _parse_and_rc(resp: bytes) -> tuple[str, dict, str | None]:
    try:
        mti, fields = iso8583.parse(resp)
    except Exception:
        return "", {}, None
    return mti, fields, iso8583.response_field39(fields)


def run_signon(cfg: SwitchConfig) -> FlowResult:
    req = iso8583.build_network_0800()
    sock = _connect(cfg)
    try:
        resp = exchange(cfg, sock, req)
    finally:
        sock.close()
    mti, fields, rc = _parse_and_rc(resp)
    return FlowResult(
        req,
        resp,
        mti or "0810",
        fields,
        rc,
        iso8583.response_meaning(rc),
        rc in ("00", None),
        ["sign-on 0800/0810"],
    )


def run_purchase(
    cfg: SwitchConfig,
    card: EmvCard,
    amount_cents: int,
    *,
    dry_run: bool = False,
    sign_on: bool = True,
) -> FlowResult:
    req = build_purchase(cfg, card, amount_cents)
    if dry_run:
        return FlowResult(
            req,
            b"",
            "0200",
            {},
            None,
            "(dry-run)",
            False,
            ["dry-run: mensaje construido, NO enviado"],
        )
    if not cfg.host or not cfg.port:
        return FlowResult(
            req,
            b"",
            "0200",
            {},
            None,
            "(sin destino)",
            False,
            ["falta switch_host/switch_port"],
        )
    log: list[str] = []
    sock = _connect(cfg)
    try:
        if sign_on:
            so = exchange(cfg, sock, iso8583.build_network_0800())
            log.append(f"0800→0810 ({len(so)}B)")
        resp = exchange(cfg, sock, req)
    finally:
        sock.close()
    mti, fields, rc = _parse_and_rc(resp)
    return FlowResult(
        req,
        resp,
        mti or "0210",
        fields,
        rc,
        iso8583.response_meaning(rc),
        rc in ("00", "11"),
        log,
    )


def run_reversal(
    cfg: SwitchConfig,
    *,
    stan: str = "000001",
    rrn: str = "",
    amount_cents: int = 0,
    pan: str = "",
    dry_run: bool = False,
    sign_on: bool = True,
) -> FlowResult:
    req = build_reversal(cfg, stan=stan, rrn=rrn, amount_cents=amount_cents, pan=pan)
    if dry_run:
        return FlowResult(
            req,
            b"",
            "0400",
            {},
            None,
            "(dry-run)",
            False,
            ["dry-run: 0400 construido, NO enviado"],
        )
    if not cfg.host or not cfg.port:
        return FlowResult(
            req,
            b"",
            "0400",
            {},
            None,
            "(sin destino)",
            False,
            ["falta switch_host/switch_port"],
        )
    log: list[str] = []
    sock = _connect(cfg)
    try:
        if sign_on:
            exchange(cfg, sock, iso8583.build_network_0800())
            log.append("0800→0810")
        resp = exchange(cfg, sock, req)
    finally:
        sock.close()
    mti, fields, rc = _parse_and_rc(resp)
    return FlowResult(
        req,
        resp,
        mti or "0410",
        fields,
        rc,
        iso8583.response_meaning(rc),
        rc in ("00", "11"),
        log,
    )
