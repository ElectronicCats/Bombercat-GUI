"""Captura/volcado completo de una tarjeta, sobre un `Transceiver`.

Refactor funcional de la antigua `ctf.full_dump`: recorre PPSE/PSE/AIDs, hace
SELECT + GPO + lectura de registros (AFL + barrido bruto) + GET DATA, y acumula
todo en un `CardDump` inmutable con `blobs` para búsqueda de flags.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from ..core import emv
from ..core.apdu import Transceiver
from ..core.atr import describe_atr
from ..core.emv import TerminalProfile
from ..core.hexutil import to_hex
from ..core.search import Hit, search_flags
from .model import CardDump, app_to_dict, fci_hex

Progress = Callable[[str], None]


def capture_card(
    send: Transceiver,
    *,
    atr: bytes = b"",
    reader: str = "",
    profile: TerminalProfile | None = None,
    brute: bool = True,
    sweep: bool = True,
    get_data: bool = True,
    raw: bool = False,
    mode: str = "auto",
    progress: Progress | None = None,
) -> CardDump:
    """Recorre toda la tarjeta y devuelve un `CardDump`.

    `mode` decide cómo interpretar lo que hay en la antena/contacto:
      - "auto" (por defecto): intenta EMV; si no hay apps (o se pide `raw`),
        cae a lectura cruda + NDEF Type 4 — igual que el comportamiento previo.
      - "emv": solo el flujo EMV (SELECT/GPO/AFL/GET DATA); no cae a crudo
        aunque no encuentre apps (útil para no perder tiempo/ruido en una
        tarjeta que se sabe de pago).
      - "nfc": tag NFC genérico (no de pago) — se salta el descubrimiento EMV
        y va directo a NDEF Type 4 + escaneo crudo (AIDs no-EMV, ficheros).
    """

    def log(msg: str) -> None:
        if progress:
            progress(msg)

    dump = CardDump(reader=reader)
    if atr:
        dump.atr = to_hex(atr, sep=" ")
        dump.atr_info = describe_atr(atr)
        dump.add_blob("ATR", atr)

    if mode == "nfc":
        log("Modo NFC genérico: se omite el descubrimiento EMV.")
        apps = []
    else:
        log("Descubriendo aplicaciones (PPSE/PSE/AIDs)...")
        apps = emv.discover(send, brute=brute)
        log(f"  {len(apps)} aplicación(es) encontrada(s)")

    for found in apps:
        log(f"SELECT {found.aid} ({found.scheme}) [{found.source}]")
        app = emv.select_application(send, found.aid)
        app = replace(app, source=found.source, label=(app.label or found.label))
        if app.fci:
            dump.blobs.append({"source": f"{app.aid}:FCI", "hex": fci_hex(app)})

        # GPO -> AIP/AFL -> registros del AFL
        try:
            resp, app = emv.get_processing_options(send, app, profile)
            if resp.ok:
                log(
                    f"  GPO ok (AIP={to_hex(app.aip or b'')}, AFL={to_hex(app.afl or b'')})"
                )
                app = emv.read_afl_records(send, app)
        except Exception as e:  # una app rara no debe abortar el volcado
            log(f"  GPO falló: {e}")

        # Barrido bruto de registros (encuentra registros fuera del AFL)
        if sweep:
            app = emv.merge_records(app, emv.sweep_records(send))

        for r in app.records:
            dump.blobs.append(
                {"source": f"{app.aid}:SFI{r.sfi}/REC{r.number}", "hex": to_hex(r.raw)}
            )

        # GET DATA (contadores, logs, saldos, propietarios)
        if get_data:
            app = app.with_data_objects(emv.get_data_sweep(send))
            for tag, val in app.data_objects.items():
                dump.blobs.append(
                    {"source": f"{app.aid}:GETDATA {tag}", "hex": to_hex(val)}
                )

        dump.applications.append(app_to_dict(app))

    # Escaneo crudo: si se pide (raw), si se pidió modo "nfc", o si no se
    # halló ninguna app EMV (y no se pidió modo "emv" a secas), lee lo que
    # haya en la tarjeta (AIDs, registros, GET DATA, binarios) + NDEF Type 4.
    if raw or mode == "nfc" or (mode != "emv" and not apps):
        from ..core.rawscan import raw_scan, read_type4_ndef

        log("Intentando NDEF (NFC Forum Type 4)...")
        try:
            ndef_result = read_type4_ndef(send)
        except Exception:
            ndef_result = None
        if ndef_result:
            log(f"  NDEF: {ndef_result['summary']}")
            dump.blobs.append(
                {"source": "NDEF:mensaje", "hex": ndef_result["ndef_hex"]}
            )
            dump.applications.append(
                {
                    "aid": "D2760000850101",
                    "scheme": "NDEF Type 4 (NFC Forum)",
                    "source": "ndef",
                    "label": "tag NDEF",
                    "aip": None,
                    "afl": None,
                    "cardholder": {},
                    "records": [],
                    "get_data": {
                        "CC": ndef_result["cc_hex"],
                        "NDEF_FILE": ndef_result["ndef_file_id"],
                    },
                    "ndef_records": ndef_result["records"],
                }
            )

        log("Escaneo crudo (lee lo que haya conectado)...")
        # En modo "nfc" se salta el barrido ciego READ RECORD/GET DATA (hasta
        # cientos de intercambios EMV-específicos que casi nunca aplican a un
        # tag no bancario) y se va directo a SELECT de AIDs + READ BINARY: es
        # lo que de verdad encuentra contenido en tags no-EMV, y con muchos
        # menos intercambios se pierde bastante menos el campo RF de una
        # tarjeta/tag de rango corto sostenida a mano.
        scan = raw_scan(
            send, progress=log, do_records=(mode != "nfc"), do_getdata=(mode != "nfc")
        )
        dump.blobs.extend(scan.blobs())
        if not scan.is_empty():
            gd = dict(scan.get_data)
            gd.update({f"SELECT {label}": hx for label, hx in scan.selects})
            gd.update({f"BINARY {label}": hx for label, hx in scan.binaries})
            dump.applications.append(
                {
                    "aid": "RAW",
                    "scheme": "lectura cruda",
                    "source": "rawscan",
                    "label": "contenido en crudo",
                    "aip": None,
                    "afl": None,
                    "cardholder": {},
                    "records": [
                        {"sfi": s, "record": r, "hex": h} for s, r, h in scan.records
                    ],
                    "get_data": gd,
                }
            )
            log(
                f"  crudo: {len(scan.selects)} SELECT, {len(scan.records)} registros, "
                f"{len(scan.get_data)} GET DATA, {len(scan.binaries)} binarios"
            )

    log("Volcado completo.")
    return dump


def capture_reader(reader, **kw) -> CardDump:
    """Conveniencia: captura desde un `OpenReader` (toma ATR y nombre de él)."""
    atr = reader.atr() if reader.atr else b""
    name = reader.device.name if reader.device else ""
    return capture_card(reader.transceive, atr=atr, reader=name, **kw)


def find_flags(dump: CardDump, patterns=None) -> list[Hit]:
    """Busca flags en todos los blobs del volcado."""
    return search_flags(dump.all_blobs(), patterns)
