"""Escaneo **crudo** de una tarjeta ISO 7816 sobre un `Transceiver` (puro).

Cuando `discover` no encuentra una app EMV (tarjeta no-EMV, applet propietario,
sistema de ficheros, etc.), este módulo lee "lo que haya": fuerza SELECT de una
lista amplia de AIDs (de pago y no-pago), barre READ RECORD por todos los SFI,
barre GET DATA de tags comunes e intenta READ BINARY de ficheros transparentes.
Todo tolerante a errores y agnóstico de la estructura: devuelve bytes crudos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import apdu as apdumod
from . import emv
from . import ndef as ndefmod
from .aids import KNOWN_AIDS, PPSE, PSE, RIDS
from .apdu import APDU, CLA_ISO, INS_READ_BINARY, INS_SELECT, Transceiver
from .hexutil import to_hex

NDEF_AID = bytes.fromhex("D2760000850101")  # NFC Forum Type 4 Tag Application
NDEF_CC_FILE_ID = bytes.fromhex("E103")  # Capability Container

# AIDs no-EMV frecuentes (además de los de pago en KNOWN_AIDS): identidad,
# criptografía, transporte, SIM, GlobalPlatform, NDEF…
EXTRA_AIDS: dict[str, str] = {
    "A000000308000010000100": "PIV (identidad US)",
    "A00000039742544659": "GIDS (Microsoft)",
    "D27600012401": "OpenPGP",
    "A0000006472F0001": "FIDO U2F / WebAuthn",
    "A000000527200101": "YubiKey OTP",
    "A0000001510000": "GlobalPlatform ISD",
    "A000000003000000": "Visa (RID)",
    "A0000000871002": "USIM (3GPP)",
    "A0000000041010": "Mastercard (RID app)",
    "D2760000850101": "NDEF Type 4 (NFC Forum)",
    "A0000002471001": "ICAO ePassport LDS1",
    "E828BD080F": "OSE (transporte)",
    "315041592E5359532E4444463031": "PSE (1PAY, hex)",
    "325041592E5359532E4444463031": "PPSE (2PAY, hex)",
}


@dataclass
class RawScan:
    selects: list[tuple[str, str]] = field(default_factory=list)  # (etiqueta, resp hex)
    records: list[tuple[int, int, str]] = field(default_factory=list)  # (sfi, rec, hex)
    get_data: dict[str, str] = field(default_factory=dict)  # tag -> hex
    binaries: list[tuple[str, str]] = field(default_factory=list)  # (etiqueta, hex)

    def is_empty(self) -> bool:
        return not (self.selects or self.records or self.get_data or self.binaries)

    def blobs(self) -> list[dict]:
        out = [
            {"source": f"RAW:SELECT {label}", "hex": hx} for label, hx in self.selects
        ]
        out += [
            {"source": f"RAW:SFI{sfi}/REC{rec}", "hex": hx}
            for sfi, rec, hx in self.records
        ]
        out += [
            {"source": f"RAW:GETDATA {tag}", "hex": hx}
            for tag, hx in self.get_data.items()
        ]
        out += [
            {"source": f"RAW:BINARY {label}", "hex": hx} for label, hx in self.binaries
        ]
        return out


def _positive(resp) -> bool:
    """¿La respuesta trae información útil? (datos, 9000, o warning 62xx/63xx)."""
    if resp is None:
        return False
    if resp.data:
        return True
    return resp.sw == 0x9000 or resp.sw1 in (0x62, 0x63)


def _read_binary(send: Transceiver, p1: int, p2: int = 0x00):
    try:
        return send(APDU(CLA_ISO, INS_READ_BINARY, p1, p2, le=0x00))
    except Exception:
        return None


def raw_scan(
    send: Transceiver,
    *,
    max_sfi: int = 31,
    max_rec: int = 16,
    do_aids: bool = True,
    do_records: bool = True,
    do_getdata: bool = True,
    do_binary: bool = True,
    progress=None,
) -> RawScan:
    """Lee de forma cruda todo lo que responda la tarjeta. Devuelve un `RawScan`."""

    def log(msg: str):
        if progress:
            progress(msg)

    scan = RawScan()

    # 1) Barrido de registros en el contexto inicial (MF/DF por defecto).
    if do_records:
        log("crudo: barrido READ RECORD (todos los SFI)...")
        for r in emv.sweep_records(send, max_sfi=max_sfi, max_rec=max_rec):
            scan.records.append((r.sfi, r.number, to_hex(r.raw)))

    # 2) GET DATA de tags comunes.
    if do_getdata:
        log("crudo: barrido GET DATA...")
        for tag, val in emv.get_data_sweep(send).items():
            scan.get_data[tag] = to_hex(val)

    # 3) READ BINARY de ficheros transparentes (EF por SFI corto y EF actual).
    if do_binary:
        log("crudo: intentando READ BINARY...")
        resp = _read_binary(send, 0x00, 0x00)  # EF seleccionado, offset 0
        if _positive(resp) and resp.data:
            scan.binaries.append(("EF-actual", to_hex(resp.data)))
        for sfi in range(1, 31):  # EF por identificador corto
            resp = _read_binary(send, 0x80 | sfi, 0x00)
            if _positive(resp) and resp.data:
                scan.binaries.append((f"sfi{sfi}", to_hex(resp.data)))

    # 4) Fuerza SELECT: por RID (parcial, con enumeración "siguiente"), nombres
    #    PSE/PPSE y AIDs completos conocidos + no-EMV. Muchas tarjetas solo
    #    responden a la selección PARCIAL por RID (no a los AIDs completos), que
    #    es justo lo que este barrido cubre.
    if do_aids:
        log("crudo: forzando SELECT (RID parcial + AIDs de pago y no-pago)...")
        seen_fci: set[str] = set()  # dedup por FCI recuperado

        def record_select(label: str, resp) -> bool:
            hx = to_hex(resp.data)
            if hx and hx in seen_fci:
                return False
            seen_fci.add(hx)
            scan.selects.append((label, hx))
            # tras un SELECT positivo, barre unos registros de esa app
            for sfi in range(1, 11):
                for rec in range(1, 9):
                    try:
                        rr = send(apdumod.read_record(rec, sfi))
                    except Exception:
                        continue
                    if _positive(rr) and rr.data:
                        scan.records.append((sfi, rec, to_hex(rr.data)))
            return True

        # 4a) RID parcial + siguiente ocurrencia (P2=02)
        for rid_hex, scheme in RIDS.items():
            rid = bytes.fromhex(rid_hex)
            p2 = 0x00
            for _ in range(8):
                try:
                    resp = send(APDU(CLA_ISO, INS_SELECT, 0x04, p2, rid, le=0x00))
                except Exception:
                    break
                if not _positive(resp) or not record_select(
                    f"{rid_hex} (RID {scheme})", resp
                ):
                    break
                p2 = 0x02

        # 4b) nombres PSE/PPSE
        for name in (PSE, PPSE):
            try:
                resp = send(apdumod.select(name, by_name=True))
            except Exception:
                continue
            if _positive(resp):
                record_select(name.decode("latin-1", "replace"), resp)

        # 4c) AIDs completos conocidos + no-EMV
        for aid_hex, label in {**KNOWN_AIDS, **EXTRA_AIDS}.items():
            try:
                resp = send(apdumod.select(bytes.fromhex(aid_hex), by_name=True))
            except Exception:
                continue
            if _positive(resp):
                record_select(f"{aid_hex} ({label})", resp)

    return scan


def read_type4_ndef(send: Transceiver) -> dict | None:
    """Lee un tag **NFC Forum Type 4** (NDEF sobre ISO 7816): selecciona la app
    NDEF, su Capability Container, localiza el fichero NDEF que este apunta y
    lo lee y parsea. `None` si el tag no es Type 4 / no tiene NDEF.

    A diferencia del barrido ciego de `raw_scan`, sigue exactamente los pasos
    de la spec (SELECT por AID → SELECT por file id → READ BINARY con
    offset), así que recupera el mensaje NDEF completo y bien formado en vez
    de fragmentos sueltos.
    """
    resp = send(apdumod.select(NDEF_AID, by_name=True))
    if not _positive(resp):
        return None

    resp = send(apdumod.select_file_id(NDEF_CC_FILE_ID))
    if resp is None or resp.sw != 0x9000:
        return None
    cc_resp = _read_binary(send, 0x00, 0x00)
    if cc_resp is None or not cc_resp.data or len(cc_resp.data) < 9:
        return None
    ccb = cc_resp.data

    # TLV "NDEF File Control" (T=0x04) dentro del CC, a partir del byte 7.
    file_id = None
    i = 7
    while i + 1 < len(ccb):
        t, length = ccb[i], ccb[i + 1]
        if t == 0x04 and length >= 6:
            file_id = ccb[i + 2 : i + 4]
            break
        i += 2 + length
    if not file_id:
        return None

    resp = send(apdumod.select_file_id(bytes(file_id)))
    if resp is None or resp.sw != 0x9000:
        return None
    hdr = _read_binary(send, 0x00, 0x00)
    if hdr is None or not hdr.data or len(hdr.data) < 2:
        return None
    nlen = (hdr.data[0] << 8) | hdr.data[1]
    msg = bytearray(hdr.data[2:])

    offset = 2 + len(msg)
    while len(msg) < nlen and offset < 0x7FFF:
        chunk = _read_binary(send, (offset >> 8) & 0x7F, offset & 0xFF)
        if chunk is None or not chunk.data:
            break
        msg += chunk.data
        offset += len(chunk.data)
    msg = bytes(msg[:nlen])

    records = ndefmod.parse_records(msg)
    return {
        "ok": True,
        "cc_hex": to_hex(ccb),
        "ndef_file_id": to_hex(bytes(file_id)),
        "ndef_hex": to_hex(msg),
        "records": [r.decoded() for r in records],
        "summary": ndefmod.summarize(records),
    }

    return scan
