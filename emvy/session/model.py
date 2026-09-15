"""Modelo serializable del volcado de una tarjeta (`CardDump`).

Compatible en JSON con los dumps de la versión anterior: mismo esquema
{atr, atr_info, reader, applications[], blobs[]}. `blobs` es la fuente para la
búsqueda de flags (`core.search`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from ..core import emv, tlv
from ..core.hexutil import from_hex, to_hex
from ..core.search import Blob


@dataclass
class CardDump:
    atr: str = ""
    atr_info: dict = field(default_factory=dict)
    reader: str = ""
    applications: list[dict] = field(default_factory=list)
    blobs: list[dict] = field(default_factory=list)  # [{source, hex}]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "CardDump":
        return cls(**json.loads(text))

    def all_blobs(self) -> list[Blob]:
        return [Blob(b["source"], b["hex"]) for b in self.blobs]

    def add_blob(self, source: str, data: bytes) -> None:
        self.blobs.append({"source": source, "hex": to_hex(data)})


def tlvs_from_dump(dump: "CardDump", aid: str | None = None):
    """Reconstruye (app_dict, TLVList) de una app de la captura: FCI + registros
    + GET DATA. Base para el análisis EMV (core.analyze) desde un dump."""
    apps = dump.applications
    app = None
    if aid:
        app = next((a for a in apps if a["aid"].upper() == aid.upper()), None)
    app = app or (apps[0] if apps else None)
    if not app:
        return None, None
    tlvs = tlv.TLVList()
    blobs = {b["source"]: b["hex"] for b in dump.blobs}
    fci = blobs.get(f"{app['aid']}:FCI")
    if fci:
        try:
            tlvs.extend(tlv.parse(from_hex(fci)))
        except Exception:
            pass
    for rec in app.get("records", []):
        try:
            tlvs.extend(tlv.parse(from_hex(rec["hex"])))
        except Exception:
            pass
    for tg, hx in (app.get("get_data") or {}).items():
        try:
            tlvs.append(tlv.tlv(tg, from_hex(hx)))
        except Exception:
            pass
    if app.get("aip") and not tlvs.find("82"):
        tlvs.append(tlv.tlv("82", from_hex(app["aip"])))
    return app, tlvs


def app_to_dict(app: emv.Application) -> dict:
    """Serializa una Application a dict legible/JSON."""
    return {
        "aid": app.aid,
        "label": app.label,
        "scheme": app.scheme,
        "source": app.source,
        "aip": to_hex(app.aip) if app.aip else None,
        "afl": to_hex(app.afl) if app.afl else None,
        "cardholder": emv.extract_cardholder(app.all_tlvs()),
        "records": [
            {"sfi": r.sfi, "record": r.number, "hex": to_hex(r.raw)}
            for r in app.records
        ],
        "get_data": {k: to_hex(v) for k, v in app.data_objects.items()},
    }


def fci_hex(app: emv.Application) -> str:
    """Reconstruye el FCI en hex (usa el codificador TLV, roundtrip fiable)."""
    if not app.fci:
        return ""
    return to_hex(tlv.encode(app.fci))


def from_bombercat(d: dict) -> CardDump:
    """Convierte el JSON del firmware BomberCat (JSON_START/END) en un CardDump,
    para integrarlo con la búsqueda de flags y las capturas de proyecto."""
    from ..core.aids import rid_scheme
    from ..payments.emvcard import EmvCard

    card = EmvCard.from_bombercat_json(d)
    dump = CardDump(reader="bombercat")
    app = {
        "aid": card.aid,
        "label": card.label,
        "scheme": rid_scheme(card.aid) if card.aid else "",
        "source": "bombercat",
        "aip": card.aip or None,
        "afl": None,
        "cardholder": {
            k: v
            for k, v in {
                "pan": card.pan_digits,
                "track2": card.track2,
                "expiry": card.expiry,
            }.items()
            if v
        },
        "records": [],
        "get_data": {},
    }
    # criptograma/transacción como get_data legible
    for name, tag in (
        ("arqc", "9F26"),
        ("atc", "9F36"),
        ("un", "9F37"),
        ("iad", "9F10"),
        ("cdol1", "8C"),
    ):
        val = getattr(card, name)
        if val:
            app["get_data"][tag] = val
    dump.applications.append(app)
    # blobs para búsqueda de flags
    for name in ("track2", "arqc", "atc", "un", "iad", "cdol1", "aip"):
        val = getattr(card, name)
        if val:
            dump.blobs.append({"source": f"bombercat:{name}", "hex": val})
    if card.pan_digits:
        dump.blobs.append(
            {"source": "bombercat:pan", "hex": to_hex(card.pan_digits.encode())}
        )
    return dump
