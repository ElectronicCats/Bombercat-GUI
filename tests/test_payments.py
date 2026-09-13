"""Tests de emvy.payments: EmvCard, ISO 8583 y análisis de criptograma."""
from emvy.core import tlv
from emvy.core.hexutil import from_hex
from emvy.payments import EmvCard, cryptogram, iso8583

_BC_JSON = {
    "ok": True, "pan": "4189143370041827",
    "track2": "4189143370041827D29092211000002600000F",
    "expiry": "2909", "aid": "A0000000031010", "aidName": "VISA",
    "aip": "2000", "atc": "002F", "arqc": "D6F5B2E0E50B0F9C",
    "iad": "06011203A02000", "un": "ED999B69",
}


# --- EmvCard ----------------------------------------------------------------
def test_emvcard_from_bombercat():
    c = EmvCard.from_bombercat_json(_BC_JSON)
    assert c.pan_digits == "4189143370041827"
    assert c.raw("arqc") == from_hex("D6F5B2E0E50B0F9C")
    assert c.aid == "A0000000031010" and c.label == "VISA"


def test_emvcard_from_dump_recovers_crypto():
    from emvy.session import from_bombercat
    dump = from_bombercat(_BC_JSON)
    c = EmvCard.from_dump(dump)
    assert c.atc == "002F" and c.arqc == "D6F5B2E0E50B0F9C" and c.un == "ED999B69"


# --- ISO 8583 ---------------------------------------------------------------
def test_iso8583_roundtrip():
    fields = {2: iso8583.bcd("4189143370041827"), 3: from_hex("000000"),
              4: iso8583.bcd_amount(500), 41: b"14400757", 49: from_hex("0484")}
    msg = iso8583.build("0200", fields)
    mti, parsed = iso8583.parse(msg)
    assert mti == "0200"
    assert parsed == fields


def test_iso8583_secondary_bitmap():
    fields = {2: iso8583.bcd("4111111111111111"), 70: b"\x00\x01"}
    # DE 70 no está en DEFAULT_SPEC -> ampliamos el spec
    spec = dict(iso8583.DEFAULT_SPEC)
    spec[70] = iso8583.FieldSpec("Network Mgmt", "fixed", 2)
    mti, parsed = iso8583.parse(iso8583.build("0800", fields, spec), spec)
    assert 70 in parsed and parsed[70] == b"\x00\x01"


def test_f55_from_emvcard():
    card = EmvCard.from_bombercat_json(_BC_JSON)
    f55 = iso8583.emv_icc(card, amount_cents=500)
    p = tlv.parse(f55)
    assert p.find("9F26").value == from_hex("D6F5B2E0E50B0F9C")  # ARQC
    assert p.find("9F36").value == from_hex("002F")              # ATC
    assert p.find("82").value == from_hex("2000")               # AIP
    # cabe como DE55 en un 0200 y hace roundtrip
    mti, parsed = iso8583.parse(iso8583.build("0200", {55: f55}))
    assert parsed[55] == f55


# --- traducción ISO 8583 (SEND / RCV) --------------------------------------
def test_mti_direction_send_and_recv():
    assert iso8583.describe_mti("0200").flow == "send"       # solicitud
    assert iso8583.describe_mti("0210").flow == "recv"       # respuesta
    assert iso8583.describe_mti("0800").flow == "send"       # gestión de red, req
    assert iso8583.describe_mti("0800").msg_class == "gestión de red"
    assert iso8583.describe_mti("0420").flow == "send"       # reverso, aviso
    assert iso8583.describe_mti("0420").function.startswith("aviso")


def test_translate_request_decodes_des():
    fields = {2: iso8583.bcd("4189143370041827"), 3: from_hex("000000"),
              4: iso8583.bcd_amount(1500), 22: iso8583.bcd("0500"),
              41: b"14400757", 49: from_hex("0484")}
    view = iso8583.translate(iso8583.build("0200", fields))
    assert view.mti.flow == "send"
    by_de = {f.de: f for f in view.des}
    assert "15.00" in by_de[4].interp                        # monto
    assert by_de[49].interp == "MXN"                         # divisa
    assert "chip" in by_de[22].interp                        # POS entry mode
    assert by_de[41].interp == "14400757"                    # Terminal ID ASCII
    assert "compra" in by_de[3].interp                       # processing code


def test_translate_response_code():
    view = iso8583.translate(iso8583.build("0210", {4: iso8583.bcd_amount(1500),
                                                    39: b"51", 41: b"14400757"}))
    assert view.mti.flow == "recv"
    rc = {f.de: f for f in view.des}[39]
    assert rc.interp.startswith("51") and "fondos insuficientes" in rc.interp


def test_translate_expands_field55_tlv():
    card = EmvCard.from_bombercat_json(_BC_JSON)
    f55 = iso8583.emv_icc(card, amount_cents=500)
    view = iso8583.translate(iso8583.build("0200", {55: f55}))
    de55 = {f.de: f for f in view.des}[55]
    assert de55.tlvs is not None
    assert de55.tlvs.find("9F26").value == from_hex("D6F5B2E0E50B0F9C")  # ARQC
    # el render textual incluye la línea del ARQC expandido
    assert "9F26" in view.text()


# --- ISO 8583: PIN block + cliente TCP -------------------------------------
def test_pin_block_iso0():
    blk = iso8583.pin_block_iso0("43219876543210987", "1234")
    assert blk.hex().upper() == "0412AC89ABCDEF67"


def test_iso_host_send_recv():
    import socket
    import threading

    from emvy.payments import iso_host

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    host, port = srv.getsockname()

    def serve():
        conn, _ = srv.accept()
        n = int.from_bytes(iso_host._recv_n(conn, 2), "big")
        body = iso_host._recv_n(conn, n)
        conn.sendall(len(body).to_bytes(2, "big") + body)   # eco
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    resp = iso_host.send_message(host, port, b"HELLO-ISO", header=2, timeout=2.0)
    srv.close()
    assert resp == b"HELLO-ISO"


# --- criptograma ------------------------------------------------------------
def test_cryptogram_gap_and_clean():
    cards = [EmvCard(pan="4189143370041827", atc="002F", arqc="AA", un="11"),
             EmvCard(pan="4189143370041827", atc="0031", arqc="BB", un="22")]
    rep = cryptogram.analyze(cards)
    assert not rep.replay_risk
    assert any(o.kind == "atc_gap" for o in rep.observations)


def test_cryptogram_detects_replay():
    cards = [EmvCard(pan="4111111111111111", atc="0005", arqc="DEAD", un="01"),
             EmvCard(pan="4111111111111111", atc="0005", arqc="DEAD", un="01")]
    rep = cryptogram.analyze(cards)
    assert rep.replay_risk
    kinds = {o.kind for o in rep.observations}
    assert "atc_dup" in kinds and ("arqc_dup" in kinds or "un_reuse" in kinds)


def test_cryptogram_un_reuse_medium():
    cards = [EmvCard(pan="5", atc="0001", arqc="A1", un="CAFE"),
             EmvCard(pan="5", atc="0002", arqc="A2", un="CAFE")]
    rep = cryptogram.analyze(cards)
    assert any(o.kind == "un_reuse" and o.severity == "medium" for o in rep.observations)
