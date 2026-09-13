"""NDEF (NFC Data Exchange Format): parseo puro de mensajes/registros.

Cubre los tipos "bien conocidos" (Well Known Type) más comunes en tags NFC del
mundo real — Texto (T) y URI (U), más un resumen legible para el resto (MIME,
externo, etc.) — suficiente para que un volcado de tarjeta muestre "lo
interesante" (una URL, un texto) sin implementar la spec NDEF entera.
"""
from __future__ import annotations

from dataclasses import dataclass

from .hexutil import ascii_printable, to_hex

# --- Type Name Format (3 bits altos del primer byte de cada registro) ------
TNF_EMPTY = 0x00
TNF_WELL_KNOWN = 0x01
TNF_MIME = 0x02
TNF_URI = 0x03
TNF_EXTERNAL = 0x04
TNF_UNKNOWN = 0x05
TNF_UNCHANGED = 0x06

_TNF_NAMES = {
    TNF_EMPTY: "vacío", TNF_WELL_KNOWN: "well-known", TNF_MIME: "MIME",
    TNF_URI: "URI", TNF_EXTERNAL: "externo", TNF_UNKNOWN: "desconocido",
    TNF_UNCHANGED: "continuación",
}

# Tabla de prefijos URI (NFC Forum URI RTD 1.0, §3.2.2)
_URI_PREFIXES = [
    "", "http://www.", "https://www.", "http://", "https://", "tel:", "mailto:",
    "ftp://anonymous:anonymous@", "ftp://ftp.", "ftps://", "sftp://", "smb://",
    "nfs://", "ftp://", "dav://", "news:", "telnet://", "imap:", "rtsp://",
    "urn:", "pop:", "sip:", "sips:", "tftp:", "btspp://", "btl2cap://",
    "btgoep://", "tcpobex://", "irdaobex://", "file://", "urn:epc:id:",
    "urn:epc:tag:", "urn:epc:pat:", "urn:epc:raw:", "urn:epc:", "urn:nfc:",
]


@dataclass(frozen=True)
class NdefRecord:
    tnf: int
    type_: bytes
    id_: bytes
    payload: bytes

    def type_str(self) -> str:
        return ascii_printable(self.type_) or to_hex(self.type_)

    def decoded(self) -> str:
        """Texto legible: decodifica Texto/URI si se reconoce el tipo bien
        conocido; si no, un resumen con TNF/tipo/longitud."""
        if self.tnf == TNF_WELL_KNOWN and self.type_ == b"T":
            return self._decode_text()
        if self.tnf == TNF_WELL_KNOWN and self.type_ == b"U":
            return self._decode_uri()
        if self.tnf == TNF_MIME:
            return f"MIME {self.type_str()}: {ascii_printable(self.payload) or to_hex(self.payload)}"
        if self.tnf == TNF_EMPTY:
            return "(registro vacío)"
        return (f"[{_TNF_NAMES.get(self.tnf, 'tnf?')} {self.type_str()}] "
                f"{len(self.payload)} bytes: {to_hex(self.payload)[:64]}")

    def _decode_text(self) -> str:
        if not self.payload:
            return "Texto: (vacío)"
        status = self.payload[0]
        lang_len = status & 0x3F
        encoding = "utf-16" if (status & 0x80) else "utf-8"
        lang = self.payload[1:1 + lang_len].decode("ascii", "replace")
        text = self.payload[1 + lang_len:]
        try:
            text = text.decode(encoding, "replace")
        except Exception:
            text = ascii_printable(text)
        return f"Texto ({lang}): {text}"

    def _decode_uri(self) -> str:
        if not self.payload:
            return "URI: (vacío)"
        idx = self.payload[0]
        prefix = _URI_PREFIXES[idx] if idx < len(_URI_PREFIXES) else ""
        rest = self.payload[1:].decode("utf-8", "replace")
        return f"URI: {prefix}{rest}"


# --- Construcción (inverso de parse_records) -------------------------------
def _uri_prefix_code(uri: str) -> tuple[int, str]:
    """Índice del prefijo URI más largo que casa + el resto de la URI."""
    best_i, best_len = 0, 0
    for i, p in enumerate(_URI_PREFIXES):
        if p and uri.startswith(p) and len(p) > best_len:
            best_i, best_len = i, len(p)
    return best_i, uri[best_len:]


def uri_payload(uri: str) -> bytes:
    code, rest = _uri_prefix_code(uri)
    return bytes([code]) + rest.encode("utf-8")


def text_payload(text: str, lang: str = "en") -> bytes:
    lang_b = lang.encode("ascii")
    return bytes([len(lang_b) & 0x3F]) + lang_b + text.encode("utf-8")


def build_record(tnf: int, type_: bytes, payload: bytes, *, mb: bool = True,
                 me: bool = True, sr: bool = True, il: bool = False,
                 id_: bytes = b"") -> bytes:
    """Codifica un registro NDEF. Con banderas explícitas para poder construir
    también registros **mal formados** (fuzzing): `sr=False` usa longitud de 4
    bytes, `il=True` añade campo ID, `me=False` omite el flag de fin, etc."""
    header = tnf & 0x07
    if mb:
        header |= 0x80
    if me:
        header |= 0x40
    if sr:
        header |= 0x10
    if il:
        header |= 0x08
    out = bytearray([header, len(type_) & 0xFF])
    if sr:
        out.append(len(payload) & 0xFF)
    else:
        out += len(payload).to_bytes(4, "big")
    if il:
        out.append(len(id_) & 0xFF)
    out += type_
    if il:
        out += id_
    out += payload
    return bytes(out)


def uri_record(uri: str, **kw) -> bytes:
    return build_record(TNF_WELL_KNOWN, b"U", uri_payload(uri), **kw)


def text_record(text: str, lang: str = "en", **kw) -> bytes:
    return build_record(TNF_WELL_KNOWN, b"T", text_payload(text, lang), **kw)


def card_record(pan: str = "", expiry: str = "", track2: str = "",
                aid: str = "", label: str = "") -> bytes:
    """Mensaje NDEF (un registro de texto) que **presenta los datos de una
    tarjeta** — PAN/expiry/track2/AID — para emular un tag NFC con ellos.

    OJO: esto NO es una emulación de tarjeta EMV funcional (el firmware/PN7150
    solo emula tag NDEF Type 4, no responde el protocolo EMV). Sirve para
    presentar los datos de una captura a un lector/teléfono NFC que lea NDEF."""
    parts = []
    if pan:
        parts.append(f"PAN={pan}")
    if expiry:
        parts.append(f"EXP={expiry}")
    if track2:
        parts.append(f"TRACK2={track2}")
    if aid:
        parts.append(f"AID={aid}")
    if label:
        parts.append(label)
    return text_record("  ".join(parts) or "(tarjeta sin datos)")


def parse_records(data: bytes) -> list[NdefRecord]:
    """Parsea un mensaje NDEF (secuencia de registros) en bytes crudos."""
    records: list[NdefRecord] = []
    i = 0
    n = len(data)
    while i < n:
        header = data[i]
        tnf = header & 0x07
        il = bool(header & 0x08)     # ID length present
        sr = bool(header & 0x10)     # short record
        i += 1
        if i >= n:
            break
        type_len = data[i]; i += 1
        if sr:
            if i >= n:
                break
            payload_len = data[i]; i += 1
        else:
            if i + 4 > n:
                break
            payload_len = int.from_bytes(data[i:i + 4], "big"); i += 4
        id_len = 0
        if il:
            if i >= n:
                break
            id_len = data[i]; i += 1
        type_ = data[i:i + type_len]; i += type_len
        id_ = data[i:i + id_len]; i += id_len
        payload = data[i:i + payload_len]; i += payload_len
        records.append(NdefRecord(tnf, type_, id_, payload))
        if header & 0x40:  # ME (message end)
            break
    return records


def find_ndef_tlv(data: bytes) -> bytes | None:
    """Busca el TLV "NDEF Message" (T=0x03) dentro de un fichero NDEF (formato
    TLV usado por Type 2/4 Tag) y devuelve su valor (el mensaje NDEF crudo)."""
    i = 0
    n = len(data)
    while i < n:
        t = data[i]
        if t == 0x00:  # NULL TLV (padding)
            i += 1
            continue
        if t == 0xFE:  # Terminator TLV
            break
        if i + 1 >= n:
            break
        length = data[i + 1]
        i += 2
        if length == 0xFF:  # longitud extendida (3 bytes)
            if i + 1 >= n:
                break
            length = (data[i] << 8) | data[i + 1]
            i += 2
        value = data[i:i + length]
        if t == 0x03:
            return value
        i += length
    return None


def summarize(records: list[NdefRecord]) -> str:
    if not records:
        return "(sin registros NDEF)"
    return " | ".join(r.decoded() for r in records)
