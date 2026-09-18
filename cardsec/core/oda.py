"""Offline Data Authentication (ODA): inventario, heurística de claves débiles y
recuperación/verificación del **certificado de clave pública del emisor** (RSA).

Puro y offline. La verificación completa de SDA/DDA/CDA requiere la clave pública
de la CA del esquema (RID+índice); si se aporta, se recupera y valida el
certificado del emisor (cabecera/tráiler/formato/hash). Sin clave de CA, se hace
inventario de los objetos ODA presentes y una estimación del tamaño de clave por
la longitud del certificado.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .hexutil import to_hex

# Tags ODA (EMV Book 2/3) y su rol.
ODA_TAGS = {
    "8F": "Índice de CA pública",
    "90": "Certificado de clave pública del emisor",
    "92": "Resto de clave pública del emisor",
    "9F32": "Exponente de clave pública del emisor",
    "9F46": "Certificado de clave pública del ICC",
    "9F47": "Exponente de clave pública del ICC",
    "9F48": "Resto de clave pública del ICC",
    "93": "Signed Static Application Data (SSAD)",
    "9F4A": "SDA Tag List",
    "9F4B": "Signed Dynamic Application Data (SDAD)",
}


@dataclass(frozen=True)
class OdaReport:
    methods_supported: list[str]  # p.ej. ["SDA", "DDA"]
    present: dict[str, str]  # tag -> nombre (los ODA presentes)
    missing_for_sda: list[str]
    sda_ready: bool
    dda_ready: bool
    ca_index: str | None
    ca_key_bits: int | None  # ~ longitud del cert del emisor (tag 90)
    issuer_key_bits: int | None  # ~ longitud del cert del ICC (tag 9F46)
    notes: list[str] = field(default_factory=list)


def _bits(value: bytes | None) -> int | None:
    return len(value) * 8 if value else None


def oda_report(tlvs) -> OdaReport:
    """Inventario ODA + capacidades (desde AIP) + heurística de tamaño de clave.

    `tlvs` es un `core.tlv.TLVList` (o cualquier objeto con `.find(tag)`)."""

    def find(tag):
        t = tlvs.find(tag)
        return t.value if t else None

    aip = find("82") or b""
    methods = []
    if len(aip) >= 1:
        if aip[0] & 0x40:
            methods.append("SDA")
        if aip[0] & 0x20:
            methods.append("DDA")
        if aip[0] & 0x01:
            methods.append("CDA")

    present = {tag: name for tag, name in ODA_TAGS.items() if tlvs.find(tag)}

    sda_needed = ["8F", "90", "9F32", "93"]
    missing_sda = [t for t in sda_needed if t not in present]
    sda_ready = not missing_sda
    dda_ready = all(t in present for t in ("8F", "90", "9F32", "9F46", "9F47"))

    ca_bits = _bits(find("90"))
    issuer_bits = _bits(find("9F46"))

    notes: list[str] = []
    for label, bits in (
        ("clave de CA (por cert emisor)", ca_bits),
        ("clave del emisor (por cert ICC)", issuer_bits),
    ):
        if bits is not None:
            if bits < 1024:
                notes.append(
                    f"{label}: ~{bits} bits → DÉBIL (rota; esquemas exigen ≥1408)"
                )
            elif bits < 1408:
                notes.append(f"{label}: ~{bits} bits → obsoleta/mínima")
    if "SDA" in methods and not dda_ready:
        notes.append(
            "Solo SDA (sin DDA/CDA): los datos estáticos son clonables/replayables"
        )

    ca_idx = find("8F")
    return OdaReport(
        methods_supported=methods,
        present=present,
        missing_for_sda=missing_sda,
        sda_ready=sda_ready,
        dda_ready=dda_ready,
        ca_index=(to_hex(ca_idx) if ca_idx else None),
        ca_key_bits=ca_bits,
        issuer_key_bits=issuer_bits,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Recuperación RSA del certificado de clave pública del emisor (Book 2, 6.3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IssuerPublicKey:
    header_ok: bool
    trailer_ok: bool
    format_ok: bool  # formato de certificado == 0x02
    hash_ok: bool  # SHA-1 recuperado coincide
    issuer_id: str  # dígitos del identificador (con relleno F)
    expiry: str  # MMYY
    serial: str
    modulus: bytes  # clave pública del emisor recuperada
    exponent: bytes
    valid: bool  # header+trailer+format+hash

    @property
    def key_bits(self) -> int:
        return len(self.modulus) * 8


def recover_issuer_pk(
    cert90: bytes,
    exp9F32: bytes,
    ca_modulus: bytes,
    ca_exponent: int,
    rem92: bytes = b"",
) -> IssuerPublicKey:
    """Recupera y valida la clave pública del emisor desde el certificado (tag
    90) usando la clave pública de la CA (`ca_modulus`, `ca_exponent`).

    Verifica cabecera 0x6A / tráiler 0xBC / formato 0x02 y el hash SHA-1 embebido.
    """
    n_ca = len(ca_modulus)
    if not cert90 or len(cert90) != n_ca:
        raise ValueError(
            f"cert (tag 90) de {len(cert90)}B no coincide con CA de {n_ca}B"
        )

    c = int.from_bytes(cert90, "big")
    m = int.from_bytes(ca_modulus, "big")
    recovered = pow(c, ca_exponent, m).to_bytes(n_ca, "big")

    header_ok = recovered[0] == 0x6A
    trailer_ok = recovered[-1] == 0xBC
    format_ok = recovered[1] == 0x02

    issuer_id = to_hex(recovered[2:6])
    expiry = to_hex(recovered[6:8])
    serial = to_hex(recovered[8:11])
    n_i = recovered[13]  # longitud de la clave del emisor
    leftmost = recovered[15 : n_ca - 21]  # N_CA - 36 bytes
    if n_i <= len(leftmost):
        modulus = leftmost[:n_i]
    else:
        modulus = leftmost + rem92[: n_i - len(leftmost)]

    hash_input = recovered[1 : n_ca - 21] + rem92 + exp9F32
    hash_ok = hashlib.sha1(hash_input).digest() == recovered[n_ca - 21 : n_ca - 1]

    valid = header_ok and trailer_ok and format_ok and hash_ok
    return IssuerPublicKey(
        header_ok=header_ok,
        trailer_ok=trailer_ok,
        format_ok=format_ok,
        hash_ok=hash_ok,
        issuer_id=issuer_id,
        expiry=expiry,
        serial=serial,
        modulus=modulus,
        exponent=exp9F32,
        valid=valid,
    )


def verify_issuer_certificate(
    tlvs, ca_modulus: bytes, ca_exponent: int
) -> IssuerPublicKey | None:
    """Conveniencia: recupera la clave del emisor tomando 90/9F32/92 de `tlvs`."""

    def find(tag):
        t = tlvs.find(tag)
        return t.value if t else None

    cert = find("90")
    exp = find("9F32")
    if not cert or not exp:
        return None
    return recover_issuer_pk(cert, exp, ca_modulus, ca_exponent, find("92") or b"")
