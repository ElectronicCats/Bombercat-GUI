"""Interpretación pura del ATR (Answer To Reset)."""

from __future__ import annotations

from .hexutil import ascii_printable, to_hex


def describe_atr(atr: bytes) -> dict:
    """Extrae campos básicos del ATR: TS, T0, historical bytes, protocolos."""
    atr = bytes(atr)
    info: dict = {"atr": to_hex(atr, sep=" "), "len": len(atr)}
    if len(atr) < 2:
        return info

    ts = atr[0]
    info["convention"] = (
        "directa (TS=3B)"
        if ts == 0x3B
        else ("inversa (TS=3F)" if ts == 0x3F else f"desconocida (TS={ts:02X})")
    )
    t0 = atr[1]
    num_hist = t0 & 0x0F
    info["historical_count"] = num_hist

    # Recorre TA/TB/TC/TD para encontrar dónde empiezan los historical bytes
    protocols = set()
    i = 1
    y = t0 >> 4
    while True:
        if y & 0x1:  # TA presente
            i += 1
        if y & 0x2:  # TB presente
            i += 1
        if y & 0x4:  # TC presente
            i += 1
        if y & 0x8:  # TD presente
            i += 1
            if i < len(atr):
                td = atr[i]
                protocols.add(td & 0x0F)
                y = td >> 4
                continue
        break

    info["protocols"] = sorted(f"T={p}" for p in protocols) or ["T=0"]
    # Historical bytes: los num_hist bytes antes del TCK (si lo hay)
    hist = atr[i + 1 : i + 1 + num_hist] if num_hist else b""
    if hist:
        info["historical"] = to_hex(hist, sep=" ")
        info["historical_ascii"] = ascii_printable(hist)
    return info
