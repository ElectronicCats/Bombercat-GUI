"""Flujo EMV de alto nivel, en estilo funcional.

Cada función recibe un `send: Transceiver` (Callable[[APDU|bytes], Response]) en
vez de un objeto con estado — así la lógica EMV es independiente del backend de
lector y testeable con un transceiver falso. `Application`/`Record` son
inmutables: las operaciones devuelven copias (`dataclasses.replace`) en lugar de
mutar. Los valores de "terminal" que alimentan los DOL llegan como un
`TerminalProfile` (dict tag->bytes), típicamente desde el proyecto activo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Mapping

from . import apdu, tlv
from .aids import KNOWN_AIDS, PPSE, PSE, rid_scheme
from .apdu import Response, Transceiver
from .hexutil import to_hex
from .track import parse_track2_emv

# Un TerminalProfile es simplemente tag_hex -> bytes, listo para build_dol.
TerminalProfile = Mapping[str, bytes]


# ---------------------------------------------------------------------------
# Perfil de terminal por defecto para construir DOLs (PDOL/CDOL/DDOL).
# Suficiente para que la tarjeta responda a GPO. NO representa una terminal real
# ni genera transacciones válidas: es solo para leer/explorar la tarjeta.
# ---------------------------------------------------------------------------
def default_terminal_profile() -> dict[str, bytes]:
    return {
        "9F02": bytes.fromhex("000000000100"),  # Amount authorised = 1.00
        "9F03": bytes.fromhex("000000000000"),  # Amount other
        "9F1A": bytes.fromhex("0484"),  # Terminal country (484 = MX)
        "5F2A": bytes.fromhex("0484"),  # Transaction currency (MXN)
        "95": bytes.fromhex("0000000000"),  # TVR
        "9A": bytes.fromhex("260101"),  # Transaction date YYMMDD
        "9C": bytes.fromhex("00"),  # Transaction type = compra
        "9F37": os.urandom(4),  # Unpredictable Number
        "9F35": bytes.fromhex("22"),  # Terminal type = online/offline att.
        "9F33": bytes.fromhex("E0F8C8"),  # Terminal capabilities
        "9F40": bytes.fromhex("F000F0A001"),  # Additional terminal caps
        "9F1E": b"EMVyCTRL",  # IFD serial (8 an)
        "9F66": bytes.fromhex("36000000"),  # TTQ (contactless)
        "9F4E": b"EMVy CTF Terminal",  # Merchant name
        "9F15": bytes.fromhex("0000"),  # MCC
        "9F16": b"EMVyCTFMERCHANT ",  # Merchant identifier (15 an)
        "9F1C": b"EMVy0001",  # Terminal id (8 an)
        "9F21": bytes.fromhex("120000"),  # Transaction time
        "9F41": bytes.fromhex("00000001"),  # Transaction sequence counter
    }


@dataclass(frozen=True)
class Record:
    sfi: int
    number: int
    raw: bytes
    tlvs: tlv.TLVList = field(default_factory=tlv.TLVList)


@dataclass(frozen=True)
class Application:
    aid: str
    label: str = ""
    scheme: str = ""
    source: str = ""  # "PSE" | "PPSE" | "bruteforce" | "select"
    priority: int | None = None
    fci: tlv.TLVList | None = None
    aip: bytes | None = None
    afl: bytes | None = None
    records: tuple[Record, ...] = ()
    data_objects: Mapping[str, bytes] = field(default_factory=dict)
    gpo_tlvs: tlv.TLVList | None = None  # TLVs del GPO (qVSDC: 57/5A/5F24/… van aquí)

    def all_tlvs(self) -> tlv.TLVList:
        out = tlv.TLVList()
        if self.fci:
            out.extend(self.fci)
        if self.gpo_tlvs:  # qVSDC: datos de tarjeta dentro del GPO
            out.extend(self.gpo_tlvs)
        for r in self.records:
            out.extend(r.tlvs)
        return out

    def with_records(self, records) -> "Application":
        return replace(self, records=tuple(records))

    def with_data_objects(self, data: Mapping[str, bytes]) -> "Application":
        return replace(self, data_objects=dict(data))


# ---------------------------------------------------------------------------
# SELECT / PSE / PPSE
# ---------------------------------------------------------------------------
def select_name(send: Transceiver, name: bytes) -> tuple[Response, tlv.TLVList]:
    resp = send(apdu.select(name, by_name=True))
    parsed = tlv.parse(resp.data) if resp.data else tlv.TLVList()
    return resp, parsed


def _app_from_template(tmpl: tlv.TLV, source: str) -> Application | None:
    aid_t = tmpl.find("4F")
    if not aid_t:
        return None
    label = tmpl.find("50")
    prio = tmpl.find("87")
    return Application(
        aid=to_hex(aid_t.value),
        label=(label.interpret().strip('"') if label else ""),
        scheme=rid_scheme(to_hex(aid_t.value)),
        source=source,
        priority=(prio.value[0] if prio and prio.value else None),
    )


def read_pse_directory(
    send: Transceiver, name: bytes, source: str
) -> list[Application]:
    """Selecciona el PSE/PPSE y extrae la lista de aplicaciones."""
    apps: list[Application] = []
    resp, fci = select_name(send, name)
    if not resp.ok:
        return apps

    # PPSE: los AIDs vienen en el FCI (BF0C -> 61 -> 4F/50/87)
    for tmpl in fci.find_all("61"):
        app = _app_from_template(tmpl, source)
        if app:
            apps.append(app)

    # PSE de contacto: hay que leer los registros del SFI del directorio (tag 88)
    if not apps and source == "PSE":
        sfi_t = fci.find("88")
        sfi = sfi_t.value[0] if sfi_t and sfi_t.value else 1
        for rec_num in range(1, 17):
            r = send(apdu.read_record(rec_num, sfi))
            if not r.ok:
                break
            for tmpl in tlv.parse(r.data).find_all("61"):
                app = _app_from_template(tmpl, source)
                if app:
                    apps.append(app)
    return apps


def bruteforce_aids(send: Transceiver, aid_list=None) -> list[Application]:
    """Prueba SELECT con una lista de AIDs conocidos."""
    apps: list[Application] = []
    for aid_hex in aid_list or KNOWN_AIDS.keys():
        try:
            resp, fci = select_name(send, bytes.fromhex(aid_hex))
        except Exception:
            continue
        if resp.ok or resp.sw1 in (0x62, 0x63):
            label = fci.find("50") if fci else None
            df = fci.find("84") if fci else None  # AID real puede venir en 84
            real_aid = to_hex(df.value) if df else aid_hex.upper()
            apps.append(
                Application(
                    aid=real_aid,
                    label=(label.interpret().strip('"') if label else ""),
                    scheme=rid_scheme(real_aid),
                    source="bruteforce",
                    fci=fci,
                )
            )
    return apps


def discover(send: Transceiver, brute: bool = True) -> list[Application]:
    """Descubre aplicaciones: PPSE -> PSE -> (opcional) fuerza bruta de AIDs."""
    apps = read_pse_directory(send, PPSE, "PPSE")
    apps += read_pse_directory(send, PSE, "PSE")
    seen = {a.aid for a in apps}
    if brute:
        for a in bruteforce_aids(send):
            if a.aid not in seen:
                apps.append(a)
                seen.add(a.aid)
    return apps


# ---------------------------------------------------------------------------
# SELECT de una aplicación + GPO + lectura de registros
# ---------------------------------------------------------------------------
def select_application(send: Transceiver, aid_hex: str) -> Application:
    aid_hex = aid_hex.upper().replace(" ", "")
    resp, fci = select_name(send, bytes.fromhex(aid_hex))
    label = fci.find("50")
    return Application(
        aid=aid_hex,
        scheme=rid_scheme(aid_hex),
        source="select",
        fci=fci,
        label=(label.interpret().strip('"') if label else ""),
    )


def build_pdol(app: Application, profile: TerminalProfile) -> bytes:
    """Construye el campo de datos del PDOL a partir del FCI y el perfil."""
    if not app.fci:
        return b""
    pdol_t = app.fci.find("9F38")
    if not (pdol_t and pdol_t.value):
        return b""
    dol = tlv.parse_dol(pdol_t.value)
    return tlv.build_dol(dol, dict(profile))


def get_processing_options(
    send: Transceiver, app: Application, profile: TerminalProfile | None = None
) -> tuple[Response, Application]:
    """Ejecuta GPO construyendo el PDOL desde el FCI + perfil de terminal.
    Devuelve (respuesta, aplicación_actualizada con AIP/AFL)."""
    profile = profile if profile is not None else default_terminal_profile()
    pdol_bytes = build_pdol(app, profile)
    resp = send(apdu.get_processing_options(pdol_bytes))
    if resp.ok:
        app = _parse_gpo(resp.data, app)
    return resp, app


def _parse_gpo(data: bytes, app: Application) -> Application:
    parsed = tlv.parse(data)
    fmt1 = parsed.find("80")
    if fmt1 and fmt1.value:  # formato 1: AIP(2) || AFL (los datos vienen en registros)
        return replace(app, aip=fmt1.value[:2], afl=fmt1.value[2:])
    # formato 2: template 77 con 82 (AIP), 94 (AFL) y —en qVSDC— los datos de la
    # tarjeta (57 Track2, 5A PAN, 5F24 expiry, 5F20 nombre, 9F26 AC…). Guardamos
    # los TLVs internos del 77 en gpo_tlvs para que el titular/track2 se extraigan
    # aunque no haya registros (AFL vacío es lo normal en contactless Visa).
    tmpl = parsed.find("77")
    inner = tlv.TLVList(tmpl.children) if (tmpl and tmpl.children) else parsed
    aip = inner.find("82")
    afl = inner.find("94")
    return replace(
        app,
        aip=(aip.value if aip else None),
        afl=(afl.value if afl else None),
        gpo_tlvs=inner,
    )


def parse_afl(afl: bytes) -> list[tuple[int, int, int, int]]:
    """AFL -> lista de (sfi, primer_registro, ultimo_registro, nº_offline_auth)."""
    out = []
    for i in range(0, len(afl) - 3, 4):
        b1, first, last, offl = afl[i], afl[i + 1], afl[i + 2], afl[i + 3]
        out.append((b1 >> 3, first, last, offl))
    return out


def read_afl_records(send: Transceiver, app: Application) -> Application:
    """Lee todos los registros indicados por el AFL y los adjunta a la app."""
    if not app.afl:
        return app
    records: list[Record] = []
    for sfi, first, last, _ in parse_afl(app.afl):
        for rec in range(first, last + 1):
            r = send(apdu.read_record(rec, sfi))
            if r.ok and r.data:
                records.append(Record(sfi, rec, r.data, tlv.parse(r.data)))
    return app.with_records(records)


def sweep_records(
    send: Transceiver, max_sfi: int = 31, max_rec: int = 16
) -> list[Record]:
    """Barrido bruto: intenta READ RECORD para cada SFI/registro. Útil en CTF
    para encontrar registros fuera del AFL 'oficial'."""
    found: list[Record] = []
    for sfi in range(1, max_sfi + 1):
        empty_streak = 0
        for rec in range(1, max_rec + 1):
            r = send(apdu.read_record(rec, sfi))
            if r.ok and r.data:
                found.append(Record(sfi, rec, r.data, tlv.parse(r.data)))
                empty_streak = 0
            else:
                empty_streak += 1
                if empty_streak >= 3 and rec >= 3:
                    break  # SFI probablemente vacío
    return found


def merge_records(app: Application, extra: list[Record]) -> Application:
    """Une `extra` a los registros de la app evitando duplicados (sfi, número)."""
    have = {(r.sfi, r.number) for r in app.records}
    new = [r for r in extra if (r.sfi, r.number) not in have]
    return app.with_records(list(app.records) + new)


# ---------------------------------------------------------------------------
# GET DATA
# ---------------------------------------------------------------------------
# Tags típicos accesibles vía GET DATA (contadores, logs, saldos)
COMMON_GET_DATA_TAGS = [
    0x9F36,  # ATC
    0x9F13,  # Last online ATC
    0x9F17,  # PIN try counter
    0x9F4F,  # Log format
    0x9F4D,  # Log entry
    0x9F50,  # Offline accumulator balance
    0x9F51,  # App currency code
    0x9F52,  # Application default action
    0x9F5C,  # Cumulative total
    0x9F6E,  # Form factor / third party
    0x0101,
    0x0102,  # propietarios (algunos CTF esconden aquí)
    0xBF0C,
]


def get_data(send: Transceiver, tag: int) -> Response:
    return send(apdu.get_data(tag))


def get_data_sweep(send: Transceiver, tags=None) -> dict[str, bytes]:
    """GET DATA sobre una lista de tags; devuelve los que respondan OK."""
    out: dict[str, bytes] = {}
    for tag in tags or COMMON_GET_DATA_TAGS:
        r = get_data(send, tag)
        if r.ok and r.data:
            out[f"{tag:04X}"] = r.data
    return out


# ---------------------------------------------------------------------------
# Extracción de datos del titular
# ---------------------------------------------------------------------------
def extract_cardholder(tlvs: tlv.TLVList) -> dict[str, str]:
    """Extrae PAN, expiración, nombre y Track2 (datos legibles de la tarjeta)."""
    out: dict[str, str] = {}
    pan = tlvs.find("5A")
    track2 = tlvs.find("57")
    if pan:
        out["pan"] = to_hex(pan.value).rstrip("F")
    if track2 and track2.value:
        out["track2"] = to_hex(track2.value)
        t2 = parse_track2_emv(track2.value)
        if t2:
            out.setdefault("pan", t2.pan)
            if t2.expiry:
                out["expiry_track2"] = t2.expiry
            if t2.service_code:
                out["service_code"] = t2.service_code
    exp = tlvs.find("5F24")
    if exp:
        out["expiry"] = to_hex(exp.value)  # YYMMDD
    name = tlvs.find("5F20")
    if name:
        out["cardholder"] = name.interpret().strip('"')
    psn = tlvs.find("5F34")
    if psn:
        out["pan_seq"] = to_hex(psn.value)
    return out
