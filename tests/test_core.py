"""Tests del núcleo puro (sin hardware): TLV, DOL, APDU, ATR, AID, track, search."""

from cardsec.core import apdu, atr, search, tlv, track
from cardsec.core.aids import rid_scheme
from cardsec.core.hexutil import from_hex, to_hex


# --- TLV --------------------------------------------------------------------
def test_tlv_parse_basic():
    data = tlv.encode(
        [
            tlv.tlv("5A", from_hex("4761739001010010")),
            tlv.tlv("5F24", from_hex("251231")),
        ]
    )
    parsed = tlv.parse(data)
    assert parsed.find("5A").value == from_hex("4761739001010010")
    assert parsed.find("5F24").value == from_hex("251231")


def test_tlv_nested_ppse():
    fci = tlv.TLV(
        "6F",
        b"",
        [
            tlv.tlv("84", b"2PAY.SYS.DDF01"),
            tlv.TLV(
                "A5",
                b"",
                [
                    tlv.TLV(
                        "BF0C",
                        b"",
                        [
                            tlv.TLV(
                                "61",
                                b"",
                                [tlv.tlv("4F", from_hex("A0000000041010"))],
                                constructed=True,
                            ),
                        ],
                        constructed=True,
                    )
                ],
                constructed=True,
            ),
        ],
        constructed=True,
    )
    parsed = tlv.parse(tlv.encode_tlv(fci))
    assert to_hex(parsed.find("4F").value) == "A0000000041010"
    assert parsed.find("84").value == b"2PAY.SYS.DDF01"


def test_tlv_encode_roundtrip_multibyte_and_long():
    # tag de 2 bytes + valor largo (>127 -> longitud forma larga)
    big = tlv.tlv("9F46", b"\xaa" * 200)
    parsed = tlv.parse(tlv.encode_tlv(big))
    assert parsed.find("9F46").value == b"\xaa" * 200


def test_encode_len_forms():
    assert tlv.encode_len(0x7F) == b"\x7f"
    assert tlv.encode_len(0x80) == b"\x81\x80"
    assert tlv.encode_len(0x100) == b"\x82\x01\x00"


# --- DOL --------------------------------------------------------------------
def test_dol_parse_and_build():
    dol = tlv.parse_dol(from_hex("9F3704" "9F0206" "DF0102"))
    assert dol == [("9F37", 4), ("9F02", 6), ("DF01", 2)]
    vals = {"9F37": from_hex("11223344"), "9F02": from_hex("000000000100")}
    built = tlv.build_dol(dol, vals)
    assert built == from_hex("11223344" "000000000100" "0000")  # DF01 -> pad ceros


# --- APDU -------------------------------------------------------------------
def test_apdu_build():
    a = apdu.select(b"2PAY.SYS.DDF01")
    assert str(a).replace(" ", "") == "00A404000E" + to_hex(b"2PAY.SYS.DDF01") + "00"
    assert str(apdu.get_data(0x9F36)).replace(" ", "") == "80CA9F3600"


def test_status_words():
    assert apdu.status_word(0x90, 0x00) == "OK"
    assert apdu.status_word(0x61, 0x1C).startswith("Hay 28")
    assert "exacta" in apdu.status_word(0x6C, 0x0A)
    assert "3 intentos" in apdu.status_word(0x63, 0xC3)


def test_make_transceiver_get_response_and_6c():
    """Simula un transmit de bajo nivel con 6C (Le) y 61 (GET RESPONSE)."""
    script = {
        # comando original con Le=00 -> responde 6C05 (longitud exacta 5)
        "00B2010C00": (b"", 0x6C, 0x05),
        # reintento con Le=05 -> 61 03 (hay 3 bytes con GET RESPONSE)
        "00B2010C05": (b"", 0x61, 0x03),
        # GET RESPONSE Le=03 -> datos + 9000
        "00C0000003": (from_hex("AABBCC"), 0x90, 0x00),
    }
    calls = []

    def transmit(b):
        calls.append(to_hex(b))
        return script[to_hex(b)]

    send = apdu.make_transceiver(transmit)
    resp = send(apdu.read_record(1, 1))
    assert resp.ok and resp.data == from_hex("AABBCC"), (resp, calls)


# --- ATR / AID --------------------------------------------------------------
def test_describe_atr():
    info = atr.describe_atr(from_hex("3B00"))
    assert info["convention"].startswith("directa")


def test_rid_scheme():
    assert "Mastercard" in rid_scheme("A0000000041010")
    assert "Visa" in rid_scheme("A0000000031010")


# --- Track (banda magnética) ------------------------------------------------
def test_track1():
    t = track.parse_track1("%B4761739001010010^DOE/JOHN^25122010000000000?")
    assert t.pan == "4761739001010010" and t.name == "DOE/JOHN"
    assert t.expiry == "2512" and t.service_code == "201"


def test_track2_and_emv():
    t = track.parse_track2(";4761739001010010=25122010000000?")
    assert (
        t.pan == "4761739001010010" and t.expiry == "2512" and t.service_code == "201"
    )
    e = track.parse_track2_emv(from_hex("4761739001010010D2512201" + "F" * 4))
    assert e.pan == "4761739001010010" and e.expiry == "2512"


def test_build_track2_emv_roundtrip():
    """build_track2_emv es el inverso de parse_track2_emv (para regenerar el
    track2 al editar PAN/caducidad en el editor de tarjetas)."""
    t2 = track.build_track2_emv("4189143370041827", "2909", "221", "1000002600000")
    assert t2.startswith("4189143370041827D2909221")
    assert len(t2) % 2 == 0  # nibble par (relleno F)
    p = track.parse_track2_emv(t2)
    assert (
        p.pan == "4189143370041827" and p.expiry == "2909" and p.service_code == "221"
    )
    # PAN editado → el nuevo track2 lleva el PAN nuevo
    t2b = track.build_track2_emv("4111111111111111", "2512", "201")
    assert track.parse_track2_emv(t2b).pan == "4111111111111111"


def test_parse_swipe_combined():
    raw = "%B4761739001010010^DOE/JOHN^25122010?;4761739001010010=25122010?"
    out = track.parse_swipe(raw)
    assert "track1" in out and "track2" in out


# --- búsqueda de flags ------------------------------------------------------
def test_flag_search_ascii_and_hexgap():
    rec = tlv.encode_tlv(tlv.tlv("DFAE01", b"flag{emv_ctf_pwn}"))
    hits = search.search_flags([search.Blob("SFI2/REC1", to_hex(rec))])
    assert any(h.match == "flag{emv_ctf_pwn}" for h in hits)
    # flag partida por bytes no imprimibles -> se recupera vía hex-decoded
    raw = b"fl\x00ag{ctf_hi\xffdden}"
    hits2 = search.search_regex([search.Blob("x", to_hex(raw))], r"flag\{[^}]+\}")
    assert any("flag{ctf_hidden}" in h.match for h in hits2)
