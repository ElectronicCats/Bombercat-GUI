"""Núcleo puro de EMVyController: sin IO, sin estado global.

Todo lo que se pueda calcular sin tarjeta ni lector vive aquí y es testeable en
aislamiento (pasando un `Transceiver` falso a las funciones de `emv`).
"""
from __future__ import annotations

from . import aids, apdu, atr, emv, hexutil, search, tags, tlv, track  # noqa: F401

__all__ = [
    "aids", "apdu", "atr", "emv", "hexutil", "search", "tags", "tlv", "track",
]
