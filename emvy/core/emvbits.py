"""Decodificadores de campos de bits EMV (puros): AIP, AUC, TTQ.

Cada campo se describe como una lista de `(byte, bit, nombre)` (bit 8 = MSB) y se
decodifica a una lista de `Flag(nombre, set)`. Útil para interpretar capacidades
de la tarjeta/terminal en el Explorador y en el análisis de seguridad.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Flag:
    name: str
    is_set: bool


def _decode(data: bytes, spec: list[tuple[int, int, str]]) -> list[Flag]:
    out: list[Flag] = []
    for byte_i, bit, name in spec:
        if byte_i < len(data):
            mask = 1 << (bit - 1)
            out.append(Flag(name, bool(data[byte_i] & mask)))
        else:
            out.append(Flag(name, False))
    return out


def set_flags(flags: list[Flag]) -> list[str]:
    """Nombres de los bits activos (para un resumen compacto)."""
    return [f.name for f in flags if f.is_set]


# --- AIP (tag 82): Application Interchange Profile --------------------------
_AIP = [
    (0, 7, "SDA soportado"),
    (0, 6, "DDA soportado"),
    (0, 5, "Verificación de titular (CVM) soportada"),
    (0, 4, "Gestión de riesgo del terminal requerida"),
    (0, 3, "Autenticación del emisor soportada"),
    (0, 2, "CVM en el dispositivo (CDCVM) soportado"),
    (0, 1, "CDA soportado"),
    (1, 8, "Modo EMV (contactless) soportado"),
    (1, 1, "Protocolo anti-relay (RRP) soportado"),
]


def decode_aip(data: bytes) -> list[Flag]:
    return _decode(data, _AIP)


# --- AUC (tag 9F07): Application Usage Control ------------------------------
_AUC = [
    (0, 8, "Válida para efectivo doméstico"),
    (0, 7, "Válida para efectivo internacional"),
    (0, 6, "Válida para bienes domésticos"),
    (0, 5, "Válida para bienes internacionales"),
    (0, 4, "Válida para servicios domésticos"),
    (0, 3, "Válida para servicios internacionales"),
    (0, 2, "Válida en cajeros (ATM)"),
    (0, 1, "Válida en terminales no-ATM"),
    (1, 8, "Cashback doméstico permitido"),
    (1, 7, "Cashback internacional permitido"),
]


def decode_auc(data: bytes) -> list[Flag]:
    return _decode(data, _AUC)


# --- TTQ (tag 9F66): Terminal Transaction Qualifiers (contactless) ---------
_TTQ = [
    (0, 8, "MSD soportado"),
    (0, 6, "EMV modo soportado"),
    (0, 5, "EMV por contacto soportado"),
    (0, 4, "Lector solo-offline"),
    (0, 3, "PIN online soportado"),
    (0, 2, "Firma soportada"),
    (0, 1, "ODA para autorización online soportada"),
    (1, 8, "Criptograma online requerido"),
    (1, 7, "CVM requerido"),
    (1, 6, "PIN offline por contacto soportado"),
    (2, 8, "Issuer Update Processing soportado"),
    (2, 7, "CDCVM (Consumer Device CVM) soportado"),
]


def decode_ttq(data: bytes) -> list[Flag]:
    return _decode(data, _TTQ)
