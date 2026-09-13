"""Utilidades puras de hex/bytes/ASCII. Sin IO, sin estado — todo son funciones.

Base reutilizada por casi todo el proyecto: APDUs, TLV, pistas y volcados.
"""
from __future__ import annotations

from typing import Iterable

Bytesish = bytes | bytearray | Iterable[int]


def to_hex(data: Bytesish, sep: str = "") -> str:
    """Bytes -> string hex en mayúsculas. `sep` separa cada byte."""
    return sep.join(f"{b:02X}" for b in bytes(data))


def from_hex(text: str) -> bytes:
    """String hex (con o sin espacios/':'/'0x') -> bytes."""
    cleaned = (
        text.replace("0x", "")
        .replace("0X", "")
        .replace(":", "")
        .replace(" ", "")
        .replace("\n", "")
        .replace("\t", "")
    )
    if len(cleaned) % 2:
        raise ValueError(f"hex de longitud impar: {text!r}")
    return bytes.fromhex(cleaned)


def is_hex(text: str) -> bool:
    """True si `text` es hex válido (tras limpiar separadores)."""
    try:
        from_hex(text)
        return True
    except ValueError:
        return False


def hexdump(data: Bytesish, width: int = 16, base: int = 0) -> str:
    """Hexdump clásico con offset, hex y ASCII."""
    data = bytes(data)
    out = []
    for off in range(0, len(data), width):
        chunk = data[off : off + width]
        hexs = " ".join(f"{b:02X}" for b in chunk)
        hexs = f"{hexs:<{width * 3 - 1}}"
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{base + off:08X}  {hexs}  |{ascii_}|")
    return "\n".join(out)


def ascii_printable(data: Bytesish, placeholder: str = ".") -> str:
    """Cada byte imprimible como carácter; el resto -> `placeholder`."""
    return "".join(chr(b) if 32 <= b < 127 else placeholder for b in bytes(data))


def ascii_only(data: Bytesish) -> str:
    """Solo los bytes imprimibles concatenados (sin placeholder).

    Útil para buscar cadenas que atraviesan bytes no-ASCII intercalados.
    """
    return "".join(chr(b) if 32 <= b < 127 else "" for b in bytes(data))


def chunk(data: bytes, size: int) -> list[bytes]:
    """Parte `data` en trozos de `size` bytes (el último puede ser menor)."""
    return [data[i : i + size] for i in range(0, len(data), size)]
