"""Búsqueda de flags / patrones sobre fragmentos de datos de la tarjeta.

Puro: opera sobre `Blob`s (fragmentos etiquetados) y devuelve `Hit`s. Busca cada
patrón como ASCII directo, decodificando el hex a ASCII (saltando bytes no
imprimibles) y en la representación hex textual.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .hexutil import ascii_only, ascii_printable, from_hex, to_hex

# Patrones de flag habituales en CTF (case-insensitive por defecto)
DEFAULT_FLAG_PATTERNS = [
    r"flag\{[^}]{0,120}\}",
    r"ctf\{[^}]{0,120}\}",
    r"[A-Za-z0-9_]{2,20}\{[^}]{2,120}\}",  # genérico xxx{...}
    r"FLAG[-_: ][A-Za-z0-9_]{4,}",
]


@dataclass(frozen=True)
class Blob:
    """Un fragmento de datos etiquetado, para búsqueda de flags."""
    source: str      # p.ej. "ATR", "A000...:SFI2/REC1", "GETDATA 9F4F"
    hex: str

    @property
    def raw(self) -> bytes:
        return from_hex(self.hex)


@dataclass(frozen=True)
class Hit:
    source: str
    match: str
    where: str   # "ascii" | "hex-decoded" | "hex"
    context: str


def search(blobs: list[Blob], patterns=None, case_insensitive: bool = True) -> list[Hit]:
    """Busca `patterns` en cada blob (ascii / hex-decoded / hex). Deduplica."""
    pats = patterns or DEFAULT_FLAG_PATTERNS
    flags = re.IGNORECASE if case_insensitive else 0
    compiled = [re.compile(p, flags) for p in pats]
    hits: list[Hit] = []

    for blob in blobs:
        raw = blob.raw
        candidates = [
            ("ascii", ascii_printable(raw)),
            ("hex-decoded", ascii_only(raw)),
            ("hex", to_hex(raw)),
        ]
        for where, text in candidates:
            for rx in compiled:
                for m in rx.finditer(text):
                    start = max(0, m.start() - 12)
                    end = min(len(text), m.end() + 12)
                    hits.append(Hit(blob.source, m.group(0), where, text[start:end]))

    seen = set()
    unique = []
    for h in hits:
        key = (h.source, h.match)
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return unique


# Alias históricos / de conveniencia
def search_flags(blobs: list[Blob], patterns=None, case_insensitive: bool = True) -> list[Hit]:
    return search(blobs, patterns, case_insensitive)


def search_regex(blobs: list[Blob], pattern: str, case_insensitive: bool = True) -> list[Hit]:
    """Búsqueda con un patrón arbitrario suministrado por el usuario."""
    return search(blobs, [pattern], case_insensitive)
