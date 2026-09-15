"""`EmvCard`: modelo normalizado e inmutable de una tarjeta/transacción EMV.

Puente entre las fuentes de datos (JSON del BomberCat, `session.CardDump`) y los
consumidores (análisis de criptograma, ISO 8583, PoCs). Guarda los campos tal
como llegan (hex en mayúsculas para binarios; dígitos para PAN/fechas) y ofrece
accesores en bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from ..core.hexutil import from_hex, to_hex
from ..core.track import parse_track2_emv

_HEX_FIELDS = (
    "track2",
    "aid",
    "aip",
    "atc",
    "arqc",
    "iad",
    "un",
    "cdol1",
    "ttq",
    "cvm_results",
)


def _norm_hex(v: str | None) -> str:
    return (v or "").replace(" ", "").upper()


@dataclass(frozen=True)
class EmvCard:
    pan: str = ""
    track2: str = ""  # hex del Track2 equivalent (con separador D y padding F)
    expiry: str = ""  # YYMM o YYMMDD
    aid: str = ""
    label: str = ""
    aip: str = ""
    atc: str = ""  # hex (2 bytes)
    arqc: str = ""  # hex (8 bytes)
    iad: str = ""  # hex
    un: str = ""  # hex (4 bytes)
    cdol1: str = ""  # hex
    ttq: str = ""  # hex (4 bytes)
    cvm_results: str = ""  # hex (3 bytes)
    txn_date: str = ""  # YYMMDD
    amount_cents: int = 0
    extra: Mapping[str, str] = field(default_factory=dict)

    # -- accesores en bytes -------------------------------------------------
    def raw(self, name: str) -> bytes:
        val = getattr(self, name)
        return from_hex(val) if val else b""

    @property
    def pan_digits(self) -> str:
        """PAN en dígitos: del campo pan o, si falta, del Track2."""
        if self.pan:
            return self.pan.rstrip("F")
        t2 = parse_track2_emv(self.track2) if self.track2 else None
        return t2.pan if t2 else ""

    # -- construcción -------------------------------------------------------
    @classmethod
    def from_bombercat_json(cls, d: Mapping) -> "EmvCard":
        """Mapea el JSON del firmware BomberCat (JSON_START/END) a EmvCard."""
        get = d.get
        return cls(
            pan=str(get("pan", "")),
            track2=_norm_hex(get("track2")),
            expiry=str(get("expiry", "")),
            aid=_norm_hex(get("aid")),
            label=str(get("aidName") or get("label") or ""),
            aip=_norm_hex(get("aip")),
            atc=_norm_hex(get("atc")),
            arqc=_norm_hex(get("arqc")),
            iad=_norm_hex(get("iad")),
            un=_norm_hex(get("un")),
            cdol1=_norm_hex(get("cdol1")),
            ttq=_norm_hex(get("ttq")),
            cvm_results=_norm_hex(get("cvmResults") or get("cvm_results")),
            txn_date=str(get("txn_date", "")),
            amount_cents=int(get("amount_cents", 0) or 0),
            extra={k: str(v) for k, v in d.items() if k not in _BOMBERCAT_KEYS},
        )

    @classmethod
    def from_dump(cls, dump) -> "EmvCard":
        """Extrae lo disponible de un `session.CardDump`: PAN/Track2/AID/AIP/expiry
        y, si están en `get_data` (p.ej. capturas BomberCat), ARQC/ATC/UN/IAD."""
        if not dump.applications:
            return cls()
        app = dump.applications[0]
        ch = app.get("cardholder") or {}
        gd = app.get("get_data") or {}
        return cls(
            pan=str(ch.get("pan", "")),
            track2=_norm_hex(ch.get("track2")),
            expiry=str(ch.get("expiry") or ch.get("expiry_track2") or ""),
            aid=_norm_hex(app.get("aid")),
            label=str(app.get("label", "")),
            aip=_norm_hex(app.get("aip")),
            arqc=_norm_hex(gd.get("9F26")),
            atc=_norm_hex(gd.get("9F36")),
            un=_norm_hex(gd.get("9F37")),
            iad=_norm_hex(gd.get("9F10")),
        )

    def merged(self, **changes) -> "EmvCard":
        return replace(self, **{k: v for k, v in changes.items() if v is not None})

    def to_dict(self) -> dict:
        out = {
            k: getattr(self, k)
            for k in (
                "pan",
                "track2",
                "expiry",
                "aid",
                "label",
                "aip",
                "atc",
                "arqc",
                "iad",
                "un",
                "cdol1",
                "ttq",
                "cvm_results",
                "txn_date",
                "amount_cents",
            )
        }
        if self.extra:
            out["extra"] = dict(self.extra)
        return out


_BOMBERCAT_KEYS = {
    "ok",
    "pan",
    "track2",
    "expiry",
    "aid",
    "aidName",
    "label",
    "aip",
    "atc",
    "arqc",
    "iad",
    "un",
    "cdol1",
    "ttq",
    "cvmResults",
    "cvm_results",
    "txn_date",
    "amount_cents",
}
