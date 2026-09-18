"""Codec ISO 8583 genérico (build/parse) + ensamblado del campo 55 (ICC/EMV).

Genérico y **sin objetivos hardcodeados**: opera a nivel de bytes. Cada data
element (DE) tiene un `FieldSpec` (fijo / LLVAR / LLLVAR); el contenido del campo
son bytes que aporta el llamador (BCD/ASCII/binario según el DE). `build` y
`parse` son inversos: `parse(build(mti, campos)) == (mti, campos)`.

Los encoders semánticos (BCD, monto, F55 desde un `EmvCard`) van encima.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import tlv, track
from ..core.hexutil import ascii_printable, from_hex, to_hex
from .emvcard import EmvCard


# ---------------------------------------------------------------------------
# BCD
# ---------------------------------------------------------------------------
def bcd(digits: str) -> bytes:
    """'1234' -> b'\\x12\\x34' (padding 'F' a la derecha si es impar)."""
    if len(digits) % 2:
        digits += "F"
    return bytes(int(digits[i : i + 2], 16) for i in range(0, len(digits), 2))


def unbcd(data: bytes) -> str:
    """b'\\x12\\x34' -> '1234'."""
    return to_hex(data)


def bcd_amount(cents: int, nbytes: int = 6) -> bytes:
    """Monto en centavos -> BCD de `nbytes` (12 dígitos por defecto)."""
    return bcd(str(cents).zfill(nbytes * 2))


def pin_block_iso0(pan: str, pin: str) -> bytes:
    """Bloque de PIN ISO 9564 formato 0 **en claro** (previo al cifrado 3DES).

    PIN field: '0' + longitud + dígitos + relleno 'F'. PAN field: '0000' + los 12
    dígitos más a la derecha del PAN excluyendo el dígito verificador. Se hace XOR.
    El cifrado del bloque requiere una clave/HSM (fuera de alcance).
    """
    pin = "".join(ch for ch in str(pin) if ch.isdigit())
    if not 4 <= len(pin) <= 12:
        raise ValueError("el PIN debe tener entre 4 y 12 dígitos")
    pin_field = f"0{len(pin):X}{pin}".ljust(16, "F")
    digits = "".join(ch for ch in str(pan) if ch.isdigit())
    acct = digits[:-1][-12:].rjust(12, "0")  # 12 dígitos sin el verificador
    pan_field = "0000" + acct
    return (int(pin_field, 16) ^ int(pan_field, 16)).to_bytes(8, "big")


# ---------------------------------------------------------------------------
# Bitmap
# ---------------------------------------------------------------------------
def pack_bitmap(bits: set[int]) -> bytes:
    """Bitmap primario (+ secundario si hay DE>64). Activa bit 1 si aplica."""
    bits = set(bits)
    n_bytes = 16 if any(b > 64 for b in bits) else 8
    if n_bytes == 16:
        bits.add(1)
    out = bytearray(n_bytes)
    for b in bits:
        if 1 <= b <= n_bytes * 8:
            out[(b - 1) // 8] |= 0x80 >> ((b - 1) % 8)
    return bytes(out)


def unpack_bitmap(data: bytes, i: int = 0) -> tuple[set[int], int]:
    """Lee bitmap primario (+ secundario si bit 1). Devuelve (DEs, offset)."""
    bits: set[int] = set()
    for k in range(8):
        byte = data[i + k]
        for j in range(8):
            if byte & (0x80 >> j):
                bits.add(k * 8 + j + 1)
    i += 8
    if 1 in bits:
        for k in range(8):
            byte = data[i + k]
            for j in range(8):
                if byte & (0x80 >> j):
                    bits.add(64 + k * 8 + j + 1)
        i += 8
    bits.discard(1)
    return bits, i


# ---------------------------------------------------------------------------
# Especificación de campos
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FieldSpec:
    name: str
    vartype: str = "fixed"  # "fixed" | "llvar" | "lllvar"
    length: int = 0  # bytes (solo "fixed")
    len_enc: str = "bcd2"  # "bcd2" | "bcd3" | "bin1" | "bin2" (solo var)


def _enc_len(len_enc: str, n: int) -> bytes:
    if len_enc == "bcd2":
        return bcd(str(n).zfill(2))
    if len_enc == "bcd3":
        return bcd(str(n).zfill(4))  # 4 dígitos BCD -> 2 bytes
    if len_enc == "bin1":
        return bytes([n & 0xFF])
    if len_enc == "bin2":
        return n.to_bytes(2, "big")
    raise ValueError(f"len_enc desconocido: {len_enc}")


def _dec_len(len_enc: str, data: bytes, i: int) -> tuple[int, int]:
    if len_enc == "bcd2":
        return int(to_hex(data[i : i + 1])), i + 1
    if len_enc == "bcd3":
        return int(to_hex(data[i : i + 2])), i + 2
    if len_enc == "bin1":
        return data[i], i + 1
    if len_enc == "bin2":
        return int.from_bytes(data[i : i + 2], "big"), i + 2
    raise ValueError(f"len_enc desconocido: {len_enc}")


def encode_field(spec: FieldSpec, value: bytes) -> bytes:
    if spec.vartype == "fixed":
        return bytes(value)
    return _enc_len(spec.len_enc, len(value)) + bytes(value)


def decode_field(spec: FieldSpec, data: bytes, i: int) -> tuple[bytes, int]:
    if spec.vartype == "fixed":
        return data[i : i + spec.length], i + spec.length
    n, i = _dec_len(spec.len_enc, data, i)
    return data[i : i + n], i + n


# Tabla de DEs comunes (nivel byte). Ampliable/override por el llamador.
DEFAULT_SPEC: dict[int, FieldSpec] = {
    2: FieldSpec("PAN", "llvar", len_enc="bcd2"),
    3: FieldSpec("Processing Code", "fixed", 3),
    4: FieldSpec("Amount", "fixed", 6),
    7: FieldSpec("Transmission Date/Time", "fixed", 5),
    11: FieldSpec("STAN", "fixed", 3),
    12: FieldSpec("Local Time", "fixed", 3),
    13: FieldSpec("Local Date", "fixed", 2),
    14: FieldSpec("Expiry", "fixed", 2),
    18: FieldSpec("MCC", "fixed", 2),
    22: FieldSpec("POS Entry Mode", "fixed", 2),
    23: FieldSpec("PAN Seq", "fixed", 2),
    24: FieldSpec("NII/Function Code", "fixed", 2),
    25: FieldSpec("POS Condition Code", "fixed", 1),
    35: FieldSpec("Track 2", "llvar", len_enc="bcd2"),
    37: FieldSpec("RRN", "fixed", 12),
    38: FieldSpec("Auth ID Response", "fixed", 6),
    39: FieldSpec("Response Code", "fixed", 2),
    41: FieldSpec("Terminal ID", "fixed", 8),
    42: FieldSpec("Merchant ID", "fixed", 15),
    43: FieldSpec("Card Acceptor Name", "fixed", 40),
    49: FieldSpec("Currency Code", "fixed", 2),
    52: FieldSpec("PIN Data", "fixed", 8),
    53: FieldSpec("Security Control Info", "fixed", 8),
    55: FieldSpec("ICC Data (EMV)", "lllvar", len_enc="bin2"),
    64: FieldSpec("MAC", "fixed", 8),
}


# ---------------------------------------------------------------------------
# Mensaje ISO 8583
# ---------------------------------------------------------------------------
def build(
    mti: str, fields: dict[int, bytes], spec: dict[int, FieldSpec] = DEFAULT_SPEC
) -> bytes:
    """MTI (4 dígitos) + bitmap + campos en orden. Los valores son bytes de
    contenido (ya BCD/ASCII/binario según el DE)."""
    bits = set(fields)
    out = bytearray(bcd(mti.zfill(4)))
    out += pack_bitmap(bits)
    for de in sorted(fields):
        if de not in spec:
            raise ValueError(f"DE {de} no está en el spec")
        out += encode_field(spec[de], fields[de])
    return bytes(out)


def parse(
    data: bytes, spec: dict[int, FieldSpec] = DEFAULT_SPEC
) -> tuple[str, dict[int, bytes]]:
    """Inverso de `build`. Devuelve (mti, {DE: bytes})."""
    mti = to_hex(data[0:2])
    present, i = unpack_bitmap(data, 2)
    fields: dict[int, bytes] = {}
    for de in sorted(present):
        if de not in spec:
            raise ValueError(f"DE {de} presente pero no está en el spec")
        fields[de], i = decode_field(spec[de], data, i)
    return mti, fields


def build_network_0800(stan: str | None = None, info: str = "0001") -> bytes:
    """Mensaje de gestión de red 0800 (echo/sign-on): F7 (fecha/hora), F11 (STAN),
    F70 (código de gestión, 0001 = echo). Genérico, sin objetivos hardcodeados."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stan = stan or str(now.microsecond % 1000000).zfill(6)
    spec = dict(DEFAULT_SPEC)
    spec[70] = FieldSpec("Network Mgmt Info", "fixed", 2)
    fields = {
        7: bcd(now.strftime("%m%d%H%M%S")),
        11: bcd(stan[:6].zfill(6)),
        70: from_hex(info),
    }
    return build("0800", fields, spec)


def response_field39(fields: dict[int, bytes]) -> str | None:
    """Extrae el código de respuesta (DE 39) de un mensaje parseado (ASCII o BCD)."""
    v = fields.get(39)
    if not v:
        return None
    txt = "".join(chr(b) for b in v if 32 <= b < 127)
    return (txt if txt.isdigit() else to_hex(v)).zfill(2)[-2:]


def response_meaning(code: str | None) -> str:
    """Significado (subset genérico ISO 8583) de un código de respuesta F39."""
    if not code:
        return "(sin DE 39)"
    return _RESPONSE_CODES.get(
        code, f"código {code} (no estándar / específico del switch)"
    )


# ---------------------------------------------------------------------------
# Ensamblado del campo 55 (ICC / EMV) desde un EmvCard
# ---------------------------------------------------------------------------
def emv_icc(
    card: EmvCard,
    *,
    amount_cents: int | None = None,
    terminal: dict[str, str] | None = None,
) -> bytes:
    """Construye los TLV EMV del campo 55 desde un `EmvCard` (usa core.tlv).

    Los tags críticos para verificación de ARQC deben coincidir con los que el
    chip usó en PDOL/CDOL1. Faltantes -> valores de terminal por defecto.
    """
    t = dict(_DEFAULT_TERMINAL)
    if terminal:
        t.update(terminal)
    amt = amount_cents if amount_cents is not None else card.amount_cents
    date = card.txn_date or ""
    tlvs = tlv.TLVList()

    def add(tag: str, value: bytes):
        if value:
            tlvs.append(tlv.tlv(tag, value))

    add("9F66", from_hex(card.ttq or t["ttq"]))
    add("9F26", card.raw("arqc"))
    add("9F27", bytes([0x80]))  # CID: ARQC requested
    add("9F10", card.raw("iad"))
    add("9F37", card.raw("un"))
    add("9F36", card.raw("atc"))
    add("82", card.raw("aip"))
    add("9F1A", from_hex(t["country"]))
    add("9F03", bytes(6))
    add("9F02", (amt or 0).to_bytes(6, "big"))
    add("5F2A", from_hex(t["currency"]))
    if len(date) >= 6:
        add("9A", bcd(date[:6]))
    add("9C", from_hex(t["txn_type"]))
    add("95", bytes(5))
    add("9F34", from_hex(card.cvm_results or t["cvm_results"]))
    add("9F35", from_hex(t["term_type"]))
    return tlv.encode(tlvs)


_DEFAULT_TERMINAL = {
    "ttq": "26000000",  # online req, NO CVM, kiosk
    "country": "0484",  # MX
    "currency": "0484",  # MXN
    "txn_type": "00",  # compra
    "cvm_results": "1F0002",  # NoCVM ok
    "term_type": "22",  # attended online
}


# ---------------------------------------------------------------------------
# Traducción / interpretación humana (SEND y RCV)
# ---------------------------------------------------------------------------
# Decodifica un mensaje ISO 8583 crudo a algo legible: el MTI en sus cuatro
# dígitos (versión/clase/función/origen), la dirección del flujo (envío vs
# recepción, según la función) y cada DE con su valor interpretado. Puro: la
# presentación (color) se inyecta como callable, igual que en core.tlv.

_MTI_VERSION = {
    "0": "ISO 8583:1987",
    "1": "ISO 8583:1993",
    "2": "ISO 8583:2003",
    "8": "reservado nacional",
    "9": "reservado privado",
}
_MTI_CLASS = {
    "1": "autenticación",
    "2": "autorización",
    "3": "archivo (file)",
    "4": "reverso/devolución",
    "5": "reconciliación",
    "6": "administrativo",
    "7": "fee/notificación",
    "8": "gestión de red",
    "9": "reservado",
}
# (nombre, flujo): flujo "send" sale del terminal/adquirente; "recv" lo devuelve el host.
_MTI_FUNCTION = {
    "0": ("solicitud (request)", "send"),
    "1": ("respuesta a solicitud", "recv"),
    "2": ("aviso (advice)", "send"),
    "3": ("respuesta a aviso", "recv"),
    "4": ("notificación", "send"),
    "5": ("respuesta a notificación", "recv"),
}
_MTI_ORIGIN = {
    "0": "adquirente",
    "1": "repetición del adquirente",
    "2": "emisor",
    "3": "repetición del emisor",
    "4": "otro",
    "5": "repetición de otro",
}

_PROCESSING_CODES = {
    "00": "compra de bienes/servicios",
    "01": "retiro de efectivo",
    "09": "compra con cashback",
    "17": "retiro (cuota)",
    "20": "devolución (refund)",
    "21": "depósito",
    "28": "pago",
    "30": "consulta de saldo",
    "31": "consulta",
    "40": "transferencia",
    "50": "pago de servicios",
    "72": "recarga de tiempo aire",
}
_RESPONSE_CODES = {
    "00": "aprobada",
    "01": "referir al emisor",
    "03": "comercio inválido",
    "04": "retener tarjeta",
    "05": "no honrar (do not honor)",
    "12": "transacción inválida",
    "13": "monto inválido",
    "14": "tarjeta inexistente",
    "30": "error de formato",
    "41": "tarjeta perdida",
    "43": "tarjeta robada",
    "51": "fondos insuficientes",
    "54": "tarjeta expirada",
    "55": "PIN incorrecto",
    "57": "no permitida a la tarjeta",
    "58": "no permitida al terminal",
    "61": "excede límite de retiro",
    "62": "tarjeta restringida",
    "65": "excede frecuencia de retiro",
    "75": "excede intentos de PIN",
    "91": "emisor no disponible",
    "96": "malfuncionamiento del sistema",
}
_CURRENCY_CODES = {
    "0484": "MXN",
    "0840": "USD",
    "0978": "EUR",
    "0826": "GBP",
    "0392": "JPY",
    "0124": "CAD",
    "0032": "ARS",
    "0986": "BRL",
    "0170": "COP",
    "0604": "PEN",
    "0152": "CLP",
    "0356": "INR",
    "0036": "AUD",
}
_POS_ENTRY = {
    "01": "manual",
    "02": "banda magnética",
    "05": "chip (ICC)",
    "07": "contactless (chip)",
    "80": "fallback a banda",
    "90": "banda (pista completa)",
    "91": "contactless (banda)",
    "95": "chip sin CVV confiable",
}


def _digits(value: bytes) -> str:
    """Dígitos BCD de un DE numérico (sin relleno 'F' final)."""
    return to_hex(value).upper().rstrip("F")


def _ascii(value: bytes) -> str:
    return ascii_printable(value).rstrip(".").strip()


def _interp_de(de: int, value: bytes):
    """(interp_str, tlvs|None) para un DE. Añade sólo el *significado*, sin
    repetir los dígitos que ya se ven en la columna cruda. `tlvs` sólo lo usa el
    campo 55."""
    d = _digits(value)
    if de == 2:  # PAN (ya visible en crudo)
        return "", None
    if de == 3:  # processing code
        pc = d.zfill(6)
        name = _PROCESSING_CODES.get(pc[:2], "?")
        return f"{name} (cta {pc[2:4]}→{pc[4:6]})", None
    if de == 4:
        return f"{int(d or '0') / 100:.2f} (unidades menores)", None
    if de == 7:  # MMDDhhmmss
        s = d.zfill(10)
        return f"{s[0:2]}-{s[2:4]} {s[4:6]}:{s[6:8]}:{s[8:10]}", None
    if de == 11:
        return "", None
    if de == 12:  # hhmmss
        s = d.zfill(6)
        return f"{s[0:2]}:{s[2:4]}:{s[4:6]}", None
    if de == 13:  # MMDD
        s = d.zfill(4)
        return f"{s[0:2]}-{s[2:4]}", None
    if de == 14:  # YYMM
        s = d.zfill(4)
        return f"exp {s[0:2]}-{s[2:4]}", None
    if de == 22:
        return _POS_ENTRY.get(d[:2], "?"), None
    if de == 35:  # track 2
        t2 = track.parse_track2_emv(value)
        if t2:
            return f"PAN={t2.pan} exp={t2.expiry} sc={t2.service_code}", None
        return "", None
    if de in (37, 38, 41, 42, 43):  # texto ASCII
        return _ascii(value) or "", None
    if de == 39:  # response code (ASCII o BCD)
        txt = _ascii(value)
        code = (txt if txt.isdigit() else d).zfill(2)[-2:] or "??"
        return f"{code}  ({_RESPONSE_CODES.get(code, '?')})", None
    if de == 49:  # currency
        return _CURRENCY_CODES.get(d.zfill(4), "?"), None
    if de == 55:  # ICC / EMV
        try:
            return f"{len(value)} bytes de TLV EMV", tlv.parse(value)
        except Exception:
            return to_hex(value), None
    # por defecto: hex crudo (más ASCII si parece texto)
    txt = _ascii(value)
    return (f'{to_hex(value)}  ("{txt}")' if txt else to_hex(value)), None


@dataclass(frozen=True)
class MtiView:
    mti: str
    version: str
    msg_class: str
    function: str
    origin: str
    flow: str  # "send" | "recv" | "?"

    def summary(self) -> str:
        arrow = {"send": "→ ENVÍO", "recv": "← RECEPCIÓN"}.get(self.flow, "· ?")
        return (
            f"MTI {self.mti}  [{arrow}]  "
            f"{self.version} · {self.msg_class} · {self.function} · orig: {self.origin}"
        )


@dataclass(frozen=True)
class DEView:
    de: int
    name: str
    raw: bytes
    interp: str
    tlvs: tlv.TLVList | None = None  # sólo DE 55


@dataclass(frozen=True)
class Iso8583View:
    mti: MtiView
    des: list[DEView]

    def text(self, color=None) -> str:
        if color is None:

            def color(s, *a):
                return s

        lines = [color(self.mti.summary(), "bold")]
        for f in self.des:
            head = (
                f"  DE {f.de:>3}  {color(f.name, 'cyan')}  "
                f"{color(to_hex(f.raw) or '(vacío)', 'yellow')}"
            )
            if f.interp and f.interp != to_hex(f.raw):
                head += f"  {color('→ ' + f.interp, 'green')}"
            lines.append(head)
            if f.tlvs is not None:
                for ln in f.tlvs.dump(color=color).splitlines():
                    lines.append("        " + ln)
        return "\n".join(lines)


def describe_mti(mti: str) -> MtiView:
    """Decodifica un MTI de 4 dígitos en versión/clase/función/origen + flujo."""
    m = (mti or "").zfill(4)[-4:]
    func, flow = _MTI_FUNCTION.get(m[2], ("?", "?"))
    return MtiView(
        mti=m,
        version=_MTI_VERSION.get(m[0], "?"),
        msg_class=_MTI_CLASS.get(m[1], "?"),
        function=func,
        origin=_MTI_ORIGIN.get(m[3], "?"),
        flow=flow,
    )


def translate(raw: bytes, spec: dict[int, FieldSpec] = DEFAULT_SPEC) -> Iso8583View:
    """Traduce un mensaje ISO 8583 crudo a una vista legible (SEND o RCV).

    Usa `parse` para el desempaquetado y añade la interpretación semántica de
    MTI y cada DE. La dirección (envío/recepción) se deduce del dígito de
    función del MTI, así que sirve igual para peticiones y respuestas.
    """
    mti, fields = parse(raw, spec)
    des: list[DEView] = []
    for de in sorted(fields):
        value = fields[de]
        interp, tlvs = _interp_de(de, value)
        name = spec[de].name if de in spec else f"DE{de}"
        des.append(DEView(de=de, name=name, raw=value, interp=interp, tlvs=tlvs))
    return Iso8583View(mti=describe_mti(mti), des=des)
