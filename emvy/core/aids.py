"""Registro de AIDs / RIDs conocidos y nombres PSE, para descubrimiento."""
from __future__ import annotations

# Nombres del Payment System Environment (se seleccionan como DF name)
PSE = b"1PAY.SYS.DDF01"   # contacto
PPSE = b"2PAY.SYS.DDF01"  # contactless

# RID (5 bytes) -> esquema
RIDS: dict[str, str] = {
    "A000000003": "Visa",
    "A000000004": "Mastercard",
    "A000000005": "Mastercard (US Maestro)",
    "A000000025": "American Express",
    "A000000065": "JCB",
    "A000000152": "Discover / Diners",
    "A000000324": "Discover",
    "A000000333": "UnionPay",
    "A000000277": "Interac (CA)",
    "A000000228": "SPAN2 (Saudi)",
    "A000000042": "CB (Cartes Bancaires, FR)",
    "A000000098": "Visa (US Debit)",
    "A000000620": "eftpos (AU)",
    "A000000524": "RuPay (IN)",
}

# AIDs completos conocidos (hex) -> descripción. Se usan como diccionario de
# fuerza bruta cuando el PSE/PPSE no lista aplicaciones.
KNOWN_AIDS: dict[str, str] = {
    "A0000000031010": "Visa credit/debit",
    "A000000003101001": "Visa credit",
    "A000000003101002": "Visa debit",
    "A0000000032010": "Visa Electron",
    "A0000000032020": "Visa V PAY",
    "A0000000033010": "Visa Interlink",
    "A0000000038010": "Visa Plus",
    "A0000000038002": "Visa Auth (US)",
    "A0000000041010": "Mastercard credit/debit",
    "A0000000042010": "Mastercard specific",
    "A0000000043060": "Maestro",
    "A0000000043060012": "Maestro UK",
    "A0000000046000": "Cirrus",
    "A0000000048002": "Mastercard Auth (US)",
    "A0000000050001": "Maestro UK domestic",
    "A0000000050002": "Solo",
    "A00000002501": "American Express",
    "A000000025010402": "Amex",
    "A000000025010701": "Amex ExpressPay",
    "A0000000651010": "JCB",
    "A0000001523010": "Discover",
    "A0000001524010": "Discover Zip",
    "A0000003330101": "UnionPay debit",
    "A0000003330102": "UnionPay credit",
    "A0000003331010": "UnionPay",
    "A0000002771010": "Interac",
    "A0000000429010": "CB (Cartes Bancaires)",
    "A0000006200620": "eftpos savings",
    "A0000005241010": "RuPay",
    "A0000007701111": "eID / gov (ejemplo)",
    "A00000000101": "Global Platform card manager",
    "A0000001510000": "GlobalPlatform ISD",
}


def rid_scheme(aid_hex: str) -> str:
    """Devuelve el esquema deduciendo del RID (primeros 5 bytes)."""
    aid_hex = aid_hex.upper().replace(" ", "")
    rid = aid_hex[:10]
    if aid_hex in KNOWN_AIDS:
        return KNOWN_AIDS[aid_hex]
    return RIDS.get(rid, "Desconocido")
