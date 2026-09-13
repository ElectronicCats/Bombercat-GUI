"""Parser puro de pistas de banda magnética (ISO/IEC 7813) y del Track 2
equivalente EMV (tag 57).

- Track 1 (formato B):  %B PAN ^ APELLIDO/NOMBRE ^ YYMM SC DISCRECIONAL ?
- Track 2:              ; PAN = YYMM SC DISCRECIONAL ?   (separador '=' o 'D')
- Track 3:              ; ... ?   (formato variable; se expone crudo + PAN si aplica)

Todo son funciones puras; devuelven dataclasses frozen o None si no parsea.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .hexutil import to_hex


@dataclass(frozen=True)
class Track1:
    format_code: str
    pan: str
    name: str
    expiry: str          # YYMM
    service_code: str
    discretionary: str
    raw: str


@dataclass(frozen=True)
class Track2:
    pan: str
    expiry: str          # YYMM
    service_code: str
    discretionary: str
    raw: str


@dataclass(frozen=True)
class Track3:
    pan: str
    discretionary: str
    raw: str


def _strip_sentinels(s: str) -> str:
    """Quita centinelas de inicio/fin (%, ;, ?) y espacios sobrantes."""
    return s.strip().strip("%;").split("?", 1)[0]


def parse_track1(s: str) -> Track1 | None:
    """Parsea una Track 1 formato B. Acepta con o sin '%'."""
    body = s.strip()
    if body.startswith("%"):
        body = body[1:]
    body = body.split("?", 1)[0]
    if not body or body[0] not in ("B", "A"):
        return None
    fmt, rest = body[0], body[1:]
    parts = rest.split("^")
    if len(parts) < 3:
        return None
    pan = parts[0].strip()
    name = parts[1].strip()
    tail = parts[2]
    expiry = tail[0:4]
    service = tail[4:7]
    discretionary = tail[7:]
    if not pan.isdigit():
        return None
    return Track1(fmt, pan, name, expiry, service, discretionary, s.strip())


def _split_track2_digits(digits: str) -> Track2 | None:
    """Núcleo compartido: `digits` es PAN + separador + YYMM SC discrecional."""
    m = re.match(r"^(\d+)[=D](\d{0,4})(\d{0,3})(.*)$", digits)
    if not m:
        return None
    pan, expiry, service, disc = m.groups()
    return Track2(pan, expiry, service, disc.rstrip("F"), digits)


def parse_track2(s: str) -> Track2 | None:
    """Parsea una Track 2 textual (`;PAN=YYMMSC...?` o `PAN=YYMMSC...`)."""
    body = _strip_sentinels(s)
    return _split_track2_digits(body)


def parse_track2_emv(data: bytes | str) -> Track2 | None:
    """Parsea el Track 2 Equivalent EMV (tag 57): BCD con separador 'D' y
    relleno 'F'. Acepta bytes o el hex ya en texto."""
    hexs = data if isinstance(data, str) else to_hex(data)
    return _split_track2_digits(hexs.upper())


def build_track2_emv(pan: str, expiry: str = "", service_code: str = "",
                     discretionary: str = "") -> str:
    """Construye el valor del Track2 Equivalent (tag 57) en hex: `PAN D YYMM SC
    discrecional`, con relleno 'F' a nibble par. Inverso de `parse_track2_emv`.
    Útil para regenerar el track2 tras editar PAN/caducidad en el editor."""
    pan = "".join(ch for ch in pan if ch.isdigit())
    body = pan + "D" + expiry + service_code + discretionary
    if len(body) % 2:
        body += "F"
    return body.upper()


def parse_track3(s: str) -> Track3 | None:
    """Track 3: formato variable; extrae el PAN inicial si lo hay."""
    body = _strip_sentinels(s)
    m = re.match(r"^(\d+)[=D](.*)$", body)
    if not m:
        return None
    return Track3(m.group(1), m.group(2), s.strip())


def parse_swipe(raw: str) -> dict[str, object]:
    """Detecta y parsea las pistas presentes en un swipe MSR combinado.

    Los lectores HID suelen emitir las pistas concatenadas, cada una con sus
    centinelas (`%...?`, `;...?`). Devuelve un dict con las que logre parsear.
    """
    out: dict[str, object] = {"raw": raw.strip()}
    for m in re.finditer(r"%[^?]*\?", raw):
        t1 = parse_track1(m.group(0))
        if t1:
            out["track1"] = t1
            break
    semis = re.findall(r";[^?]*\?", raw)
    if semis:
        t2 = parse_track2(semis[0])
        if t2:
            out["track2"] = t2
        if len(semis) > 1:
            t3 = parse_track3(semis[1])
            if t3:
                out["track3"] = t3
    # Fallback: una línea suelta que parezca Track 2 sin centinelas
    if "track2" not in out:
        t2 = parse_track2(raw)
        if t2:
            out["track2"] = t2
    return out
