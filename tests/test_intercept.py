"""Tests del interceptor de APDUs (Burp para EMV): parser de reglas, aplicación
a comando/respuesta y el middleware de Transceiver."""
from emvy.core import intercept as ic
from emvy.core import tlv
from emvy.core.apdu import APDU, Response
from emvy.core.hexutil import from_hex


def test_parse_rules_and_errors():
    rules, errs = ic.parse_rules(
        "# comentario\n"
        "resp set-tag 82 3900\n"
        "resp set-sw 9000 @B2\n"
        "cmd replace AA BB\n"
        "bogus\n"
    )
    assert len(rules) == 3
    assert rules[1].when_ins == 0xB2
    assert errs and any("bogus" in e or "incompleta" in e for e in errs)


def test_set_tag_in_tlv():
    data = tlv.encode([tlv.tlv("82", from_hex("2000")),
                       tlv.tlv("94", from_hex("08010100"))])
    out, ok = ic.set_tag_in(data, "82", from_hex("3900"))
    assert ok and tlv.parse(out).find("82").value == from_hex("3900")
    # tag ausente -> sin cambios
    _, ok2 = ic.set_tag_in(data, "9F36", from_hex("0001"))
    assert not ok2


def test_intercepting_rewrites_and_logs():
    rules, _ = ic.parse_rules("resp set-tag 82 3900\nresp set-sw 9000 @A8")
    events = []

    def fake_send(apdu):
        return Response(tlv.encode([tlv.tlv("82", from_hex("2000"))]), 0x69, 0x85)

    send = ic.intercepting(fake_send, rules, on_event=events.append)
    resp = send(APDU(0x80, 0xA8, 0, 0, from_hex("8300")))
    assert tlv.parse(resp.data).find("82").value == from_hex("3900")   # AIP reescrito
    assert resp.sw == 0x9000                                            # SW forzado
    assert events and events[0].modified
    assert events[0].resp_before.sw == 0x6985                           # antes del cambio


def test_intercepting_ins_filter_skips():
    rules, _ = ic.parse_rules("resp set-sw 9000 @A8")

    def fake_send(apdu):
        return Response(b"", 0x69, 0x85)

    resp = ic.intercepting(fake_send, rules)(APDU(0x00, 0xB2, 0, 0))
    assert resp.sw == 0x6985            # INS B2 != A8 -> no aplica


def test_cmd_set_tag_reaches_send():
    rules, _ = ic.parse_rules("cmd set-tag 9F02 000000000200")
    seen = {}

    def fake_send(apdu):
        seen["data"] = apdu.data
        return Response(b"", 0x90, 0x00)

    cmd_data = tlv.encode([tlv.tlv("9F02", from_hex("000000000100"))])
    ic.intercepting(fake_send, rules)(APDU(0x80, 0xA8, 0, 0, cmd_data))
    assert tlv.parse(seen["data"]).find("9F02").value == from_hex("000000000200")


def test_to_apdu_from_bytes():
    a = ic.to_apdu(from_hex("00A4040007A0000000031010"))
    assert a.ins == 0xA4 and a.data == from_hex("A0000000031010")
