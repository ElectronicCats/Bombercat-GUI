"""Tests del escaneo crudo (lee cualquier tarjeta ISO 7816) y su integración en
el scanner (capture_card) cuando no hay app EMV."""
from emvy.core import rawscan
from emvy.core.apdu import (
    INS_GET_DATA,
    INS_READ_BINARY,
    INS_READ_RECORD,
    INS_SELECT,
    APDU,
    Response,
)
from emvy.core.hexutil import from_hex
from emvy.session import capture_card


def _send_with_app():
    """Fake: responde SELECT de un AID, un registro y un GET DATA."""
    def send(cmd):
        a = cmd if isinstance(cmd, APDU) else None
        if a is None:
            return Response(b"", 0x6D, 0x00)
        if a.ins == INS_SELECT and a.data == from_hex("A0000000041010"):
            return Response(from_hex("6F088408A0000000041010"), 0x90, 0x00)
        if a.ins == INS_SELECT:
            return Response(b"", 0x6A, 0x82)
        if a.ins == INS_READ_RECORD:
            sfi, rec = (a.p2 >> 3), a.p1
            if sfi == 1 and rec == 1:
                return Response(from_hex("70055A03123456"), 0x90, 0x00)
            return Response(b"", 0x6A, 0x83)
        if a.ins == INS_GET_DATA:
            if (a.p1 << 8 | a.p2) == 0x9F36:
                return Response(from_hex("00A5"), 0x90, 0x00)
            return Response(b"", 0x6A, 0x88)
        if a.ins == INS_READ_BINARY:
            return Response(b"", 0x6A, 0x82)
        return Response(b"", 0x6D, 0x00)
    return send


def _send_no_app():
    """Fake sin app EMV: todo SELECT falla, pero hay un registro legible."""
    def send(cmd):
        a = cmd if isinstance(cmd, APDU) else None
        if a is None:
            return Response(b"", 0x6D, 0x00)
        if a.ins == INS_READ_RECORD and (a.p2 >> 3) == 2 and a.p1 == 1:
            return Response(from_hex("AABBCCDD"), 0x90, 0x00)
        if a.ins == INS_READ_BINARY and a.p1 == (0x80 | 3):
            return Response(from_hex("DEADBEEF"), 0x90, 0x00)
        return Response(b"", 0x6A, 0x82)
    return send


def test_raw_scan_finds_everything():
    scan = rawscan.raw_scan(_send_with_app())
    assert not scan.is_empty()
    assert any("A0000000041010" in label for label, _ in scan.selects)
    assert any(sfi == 1 and rec == 1 for sfi, rec, _ in scan.records)
    assert "9F36" in scan.get_data
    assert any(b["source"].startswith("RAW:SELECT") for b in scan.blobs())


def test_raw_scan_binary_and_records():
    scan = rawscan.raw_scan(_send_no_app())
    assert any(sfi == 2 and rec == 1 for sfi, rec, _ in scan.records)
    assert any(label == "sfi3" for label, _ in scan.binaries)
    assert not scan.selects                       # ningún AID respondió


def test_capture_auto_raw_when_no_app():
    dump = capture_card(_send_no_app(), atr=from_hex("3B00"))
    raw_apps = [a for a in dump.applications if a["aid"] == "RAW"]
    assert raw_apps, "debería añadirse una app RAW cuando no hay EMV"
    assert raw_apps[0]["records"]                 # trae el registro leído
    assert any(b["source"].startswith("RAW:") for b in dump.blobs)


def test_capture_raw_flag_forces_scan():
    # con app EMV presente, --raw añade además el escaneo crudo
    dump = capture_card(_send_with_app(), atr=from_hex("3B00"), raw=True)
    assert any(a["aid"] == "RAW" for a in dump.applications)
    assert any(b["source"].startswith("RAW:") for b in dump.blobs)


def test_capture_emv_mode_skips_raw_fallback():
    # mode="emv": si no hay apps, NO cae a crudo (a diferencia de "auto")
    dump = capture_card(_send_no_app(), atr=from_hex("3B00"), mode="emv")
    assert not any(a["aid"] == "RAW" for a in dump.applications)
    assert not any(b["source"].startswith("RAW:") for b in dump.blobs)


# --- NFC Forum Type 4 (NDEF) -------------------------------------------------
_NDEF_AID_HEX = "D2760000850101"


def _send_ndef_type4():
    """Fake: tag Type 4 con un único registro NDEF de texto ('hi', en inglés)."""
    ndef_msg = bytes([0xD1, 0x01, 0x05]) + b"T" + bytes([0x02]) + b"en" + b"hi"
    ccb = bytes([0x00, 0x0F, 0x20, 0x00, 0x3B, 0x00, 0x34,
                 0x04, 0x06, 0xE1, 0x04, 0x00, 0x3C, 0x00, 0xFF])
    ndef_body = bytes([0x00, len(ndef_msg)]) + ndef_msg
    state = {"cur": None}

    def send(cmd):
        a = cmd if isinstance(cmd, APDU) else None
        if a is None:
            return Response(b"", 0x6D, 0x00)
        if a.ins == INS_SELECT:
            if a.p1 == 0x04 and a.data == from_hex(_NDEF_AID_HEX):
                state["cur"] = "app"
                return Response(b"", 0x90, 0x00)
            if a.p1 == 0x00 and a.data == from_hex("E103"):
                state["cur"] = "cc"
                return Response(b"", 0x90, 0x00)
            if a.p1 == 0x00 and a.data == from_hex("E104"):
                state["cur"] = "ndef"
                return Response(b"", 0x90, 0x00)
            return Response(b"", 0x6A, 0x82)
        if a.ins == INS_READ_BINARY and a.p1 == 0x00 and a.p2 == 0x00:
            if state["cur"] == "cc":
                return Response(ccb, 0x90, 0x00)
            if state["cur"] == "ndef":
                return Response(ndef_body, 0x90, 0x00)
        return Response(b"", 0x6A, 0x82)
    return send


def test_read_type4_ndef_parses_text_record():
    result = rawscan.read_type4_ndef(_send_ndef_type4())
    assert result is not None
    assert result["ndef_file_id"].upper() == "E104"
    assert result["records"] == ["Texto (en): hi"]


def test_read_type4_ndef_none_when_not_type4():
    assert rawscan.read_type4_ndef(_send_no_app()) is None


def test_capture_nfc_mode_skips_emv_and_reads_ndef():
    dump = capture_card(_send_ndef_type4(), atr=from_hex("3B00"), mode="nfc")
    assert not any(a["source"] == "emv" for a in dump.applications)
    ndef_apps = [a for a in dump.applications if a["aid"] == _NDEF_AID_HEX]
    assert ndef_apps, "debería añadirse una app NDEF en modo nfc"
    assert ndef_apps[0]["ndef_records"] == ["Texto (en): hi"]
    assert any(b["source"] == "NDEF:mensaje" for b in dump.blobs)
