"""Tests del flujo EMV funcional con una tarjeta simulada (sin hardware)."""

from fakecard import AID, FLAG, build_fake_card

from emvy.core import emv
from emvy.core.hexutil import from_hex
from emvy.session import capture_card, find_flags


def test_discover_select_gpo_afl():
    send, _ = build_fake_card()
    apps = emv.discover(send, brute=False)
    assert apps and apps[0].aid == AID and "Mastercard" in apps[0].scheme

    app = emv.select_application(send, AID)
    assert app.label == "MASTERCARD"

    resp, app = emv.get_processing_options(send, app)
    assert resp.ok and app.aip == from_hex("1980") and app.afl == from_hex("08010100")

    app = emv.read_afl_records(send, app)
    assert app.records and app.records[0].sfi == 1


def test_pdol_built_from_profile():
    """El GPO debe recibir el PDOL construido con el perfil (9F37||9F02)."""
    send, state = build_fake_card()
    app = emv.select_application(send, AID)
    profile = {"9F37": from_hex("11223344"), "9F02": from_hex("000000009999")}
    emv.get_processing_options(send, app, profile)
    assert state["gpo_pdol"] == "11223344000000009999", state["gpo_pdol"]


def test_extract_cardholder():
    send, _ = build_fake_card()
    app = emv.select_application(send, AID)
    _, app = emv.get_processing_options(send, app)
    app = emv.read_afl_records(send, app)
    ch = emv.extract_cardholder(app.all_tlvs())
    assert ch["pan"] == "4761739001010010"
    assert ch["expiry_track2"] == "2512" and ch["service_code"] == "201"
    assert ch["cardholder"] == "EMVY/CTF TEST"


def test_gpo_format2_qvsdc_extracts_cardholder():
    """En contactless Visa (qVSDC) los datos de la tarjeta (57/5F24/5F20) vienen
    DENTRO del GPO (template 77), sin registros. _parse_gpo debe guardarlos en
    gpo_tlvs para que el titular/track2 se extraigan igual."""
    from emvy.session.model import app_to_dict

    gpo = from_hex(
        "77"
        "3A"
        "8202"
        "2000"  # AIP
        "5713"
        "4189143370041827D29092211000002600000F"  # Track2 equiv
        "5F2403"
        "290930"  # expiry YYMMDD
        "5F200C"
        "504159574156452F56495341"
    )  # nombre PAYWAVE/VISA
    app = emv._parse_gpo(gpo, emv.Application(aid="A0000000031010"))
    assert app.aip == b"\x20\x00" and not app.afl  # AFL vacío (típico)
    ch = emv.extract_cardholder(app.all_tlvs())
    assert ch["pan"] == "4189143370041827"
    assert ch["track2"].upper().startswith("4189143370041827")
    assert ch["expiry"] == "290930"
    # y llega al dump serializado (de ahí lo toma EmvCard.from_dump)
    d = app_to_dict(app)
    assert d["cardholder"]["pan"] == "4189143370041827"


def test_application_is_immutable():
    """get_processing_options no debe mutar la app original (estilo funcional)."""
    send, _ = build_fake_card()
    app0 = emv.select_application(send, AID)
    _, app1 = emv.get_processing_options(send, app0)
    assert app0.aip is None and app1.aip is not None
    assert app1 is not app0


def test_capture_and_flag_search():
    send, _ = build_fake_card()
    dump = capture_card(send, atr=from_hex("3B00"), reader="fake", brute=False)
    assert dump.applications and dump.applications[0]["aid"] == AID
    assert dump.applications[0]["get_data"].get("9F36") == "9F36020005"
    hits = find_flags(dump)
    assert any(h.match == FLAG for h in hits)


def test_get_data_sweep():
    send, _ = build_fake_card()
    data = emv.get_data_sweep(send, tags=[0x9F36, 0x9F17])
    assert data.get("9F36") == from_hex("9F36020005") and "9F17" not in data
