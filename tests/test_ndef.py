"""Tests del parseo NDEF puro (core.ndef): registros Texto/URI y TLV contenedor."""

from emvy.core import ndef


def test_parse_text_record():
    # header SR+MB+ME, TNF=well-known; type='T'; payload=status+lang+texto
    msg = bytes([0xD1, 0x01, 0x05]) + b"T" + bytes([0x02]) + b"en" + b"hi"
    records = ndef.parse_records(msg)
    assert len(records) == 1
    assert records[0].tnf == ndef.TNF_WELL_KNOWN
    assert records[0].type_ == b"T"
    assert records[0].decoded() == "Texto (en): hi"


def test_parse_uri_record():
    # prefijo 0x04 = "https://", resto = "example.com"
    payload = bytes([0x04]) + b"example.com"
    msg = bytes([0xD1, 0x01, len(payload)]) + b"U" + payload
    records = ndef.parse_records(msg)
    assert len(records) == 1
    assert records[0].decoded() == "URI: https://example.com"


def test_parse_multiple_records():
    text = bytes([0xD1 & ~0x40, 0x01, 0x05]) + b"T" + bytes([0x02]) + b"en" + b"hi"
    uri = bytes([0xD1, 0x01, 0x0C]) + b"U" + bytes([0x00]) + b"example.org"
    records = ndef.parse_records(text + uri)
    assert len(records) == 2
    assert records[1].decoded() == "URI: example.org"


def test_summarize_empty():
    assert ndef.summarize([]) == "(sin registros NDEF)"


def test_find_ndef_tlv():
    inner = bytes([0xD1, 0x01, 0x00, ord("T")])
    tlv_blob = bytes([0x03, len(inner)]) + inner + bytes([0xFE])
    found = ndef.find_ndef_tlv(tlv_blob)
    assert found == inner


def test_find_ndef_tlv_skips_padding():
    inner = bytes([0xD1, 0x01, 0x00, ord("T")])
    tlv_blob = bytes([0x00, 0x00]) + bytes([0x03, len(inner)]) + inner
    assert ndef.find_ndef_tlv(tlv_blob) == inner


def test_find_ndef_tlv_none_when_absent():
    assert ndef.find_ndef_tlv(bytes([0xFE])) is None
