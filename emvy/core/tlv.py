"""Parser y codificador BER-TLV según EMV Book 3 (tags multi-byte, longitudes
multi-byte, templates constructivos anidados) + utilidades de DOL.

Todo es puro. `parse` y `encode` son inversos estructurales:
`parse(encode(t))` preserva tags, valores y anidamiento.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .hexutil import ascii_printable, from_hex, to_hex
from .tags import is_constructed, tag_fmt, tag_name


@dataclass
class TLV:
    tag: str                      # hex en mayúsculas, p.ej. "9F36"
    value: bytes                  # valor crudo (para constructivos, los bytes hijos)
    children: list["TLV"] = field(default_factory=list)
    constructed: bool = False

    @property
    def name(self) -> str:
        return tag_name(self.tag)

    def find(self, tag: str) -> "TLV | None":
        """Primera coincidencia de `tag` en profundidad (DFS)."""
        tag = tag.upper()
        if self.tag == tag:
            return self
        for ch in self.children:
            hit = ch.find(tag)
            if hit:
                return hit
        return None

    def find_all(self, tag: str) -> list["TLV"]:
        tag = tag.upper()
        out = []
        if self.tag == tag:
            out.append(self)
        for ch in self.children:
            out.extend(ch.find_all(tag))
        return out

    def interpret(self) -> str:
        """Intenta interpretar el valor según el formato del tag."""
        return interpret_value(self.tag, self.value)

    def to_bytes(self) -> bytes:
        return encode_tlv(self)

    def dump(self, indent: int = 0, color=None) -> str:
        return _dump(self, indent, color)


class TLVList(list):
    """Lista de TLV de nivel superior con helpers de búsqueda."""

    def find(self, tag: str) -> TLV | None:
        for t in self:
            hit = t.find(tag)
            if hit:
                return hit
        return None

    def find_all(self, tag: str) -> list[TLV]:
        out = []
        for t in self:
            out.extend(t.find_all(tag))
        return out

    def to_bytes(self) -> bytes:
        return encode(self)

    def dump(self, color=None) -> str:
        return "\n".join(t.dump(0, color) for t in self)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _read_tag(data: bytes, i: int) -> tuple[str, int]:
    start = i
    b0 = data[i]
    i += 1
    if (b0 & 0x1F) == 0x1F:  # tag multi-byte
        while i < len(data) and (data[i] & 0x80):
            i += 1
        i += 1  # último byte del tag (sin bit 0x80)
    return to_hex(data[start:i]), i


def _read_len(data: bytes, i: int) -> tuple[int, int]:
    b0 = data[i]
    i += 1
    if b0 & 0x80:
        n = b0 & 0x7F
        if n == 0:  # forma indefinida: consumimos el resto
            return -1, i
        length = int.from_bytes(data[i : i + n], "big")
        i += n
        return length, i
    return b0, i


def parse(data: bytes, _depth: int = 0) -> TLVList:
    """Parsea `data` como una secuencia BER-TLV. Robusto ante padding 00/FF."""
    out = TLVList()
    data = bytes(data)
    i = 0
    n = len(data)
    while i < n:
        # padding entre TLVs (EMV permite 0x00; algunos lectores dejan 0xFF)
        if data[i] in (0x00, 0xFF):
            i += 1
            continue
        try:
            tag, i = _read_tag(data, i)
            length, i = _read_len(data, i)
        except IndexError:
            break
        if length < 0:  # longitud indefinida -> tomar el resto
            length = n - i
        value = data[i : i + length]
        i += length
        constructed = is_constructed(tag)
        children = parse(value, _depth + 1) if constructed and value else TLVList()
        out.append(TLV(tag, value, list(children), constructed))
    return out


# ---------------------------------------------------------------------------
# Codificación (inverso de parse)
# ---------------------------------------------------------------------------
def encode_len(n: int) -> bytes:
    """Codifica una longitud BER: forma corta (<128) o larga (>=128)."""
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def encode_tlv(t: TLV) -> bytes:
    """Serializa un TLV a bytes. Los constructivos con hijos se recodifican
    desde los hijos; el resto usa `value` tal cual."""
    tag = from_hex(t.tag)
    if t.constructed and t.children:
        value = b"".join(encode_tlv(ch) for ch in t.children)
    else:
        value = bytes(t.value)
    return tag + encode_len(len(value)) + value


def encode(tlvs) -> bytes:
    """Serializa una lista/TLVList de TLV a bytes."""
    return b"".join(encode_tlv(t) for t in tlvs)


def tlv(tag: str, value: bytes) -> TLV:
    """Constructor de conveniencia para un TLV primitivo."""
    return TLV(tag.upper(), bytes(value), [], is_constructed(tag))


# ---------------------------------------------------------------------------
# Interpretación de valores
# ---------------------------------------------------------------------------
def interpret_value(tag: str, value: bytes) -> str:
    fmt = tag_fmt(tag)
    hexs = to_hex(value)
    if not value:
        return "(vacío)"
    if fmt in ("an", "ans"):
        txt = ascii_printable(value).rstrip(".")
        return f'"{txt}"' if txt else hexs
    if fmt == "n":
        # BCD comprimido
        return hexs
    if fmt == "cn":  # PAN comprimido: dígitos con relleno 'F'
        return hexs.rstrip("F")
    return hexs


def _dump(t: TLV, indent: int, color) -> str:
    pad = "  " * indent
    if color is None:
        def color(s, *a):  # noqa: E306
            return s
    head = f"{pad}{color(t.tag, 'cyan', 'bold')} {color(t.name, 'grey')}"
    if t.constructed and t.children:
        lines = [head]
        for ch in t.children:
            lines.append(_dump(ch, indent + 1, color))
        return "\n".join(lines)
    interp = interpret_value(t.tag, t.value)
    raw = to_hex(t.value)
    if interp != raw and interp != "(vacío)":
        val = f"{color(raw, 'yellow')}  {color('→ ' + interp, 'green')}"
    else:
        val = color(raw or "(vacío)", "yellow")
    return f"{head}\n{pad}  {val}"


# ---------------------------------------------------------------------------
# DOL (Data Object List): parsing + construcción del valor
# ---------------------------------------------------------------------------
def parse_dol(data: bytes) -> list[tuple[str, int]]:
    """Un DOL es una concatenación de (tag, longitud). Devuelve [(tag_hex, len)]."""
    out = []
    data = bytes(data)
    i = 0
    n = len(data)
    while i < n:
        tag, i = _read_tag(data, i)
        if i >= n:
            break
        length, i = _read_len(data, i)
        out.append((tag, length))
    return out


def build_dol(dol: list[tuple[str, int]], values: dict[str, bytes]) -> bytes:
    """Construye el campo de datos para un DOL. Rellena con ceros los tags
    sin valor conocido y trunca/pad a la longitud pedida."""
    out = bytearray()
    for tag, length in dol:
        v = values.get(tag.upper(), b"")
        if len(v) < length:
            v = v + b"\x00" * (length - len(v))  # pad a la derecha con ceros
        elif len(v) > length:
            v = v[:length]
        out.extend(v)
    return bytes(out)
