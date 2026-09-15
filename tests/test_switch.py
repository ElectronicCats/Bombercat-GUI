"""Tests del flujo genérico de switch ISO 8583 (payments.switch) y de las
plantillas de PoC genéricas."""

import socket
import threading
from types import SimpleNamespace

import pytest

from emvy.core.hexutil import from_hex
from emvy.payments import EmvCard, SwitchConfig, iso8583, switch

_BC = {
    "ok": True,
    "pan": "4189143370041827",
    "track2": "4189143370041827D29092211000002600000F",
    "expiry": "2909",
    "aid": "A0000000031010",
    "aip": "2000",
    "atc": "002F",
    "arqc": "D6F5B2E0E50B0F9C",
    "iad": "06011203A02000",
    "un": "ED999B69",
}


def _card():
    return EmvCard.from_bombercat_json(_BC)


# --- SwitchConfig.from_vars -------------------------------------------------
def test_config_from_vars():
    data = {
        "switch_host": "200.53.144.37",
        "switch_port": "2347",
        "switch_tls": "1",
        "tpdu": "6000000000",
        "terminal_id": "14400757",
        "merchant_id": "8647574",
        "mcc": "5541",
    }
    cfg = SwitchConfig.from_vars(lambda k: data.get(k))
    assert cfg.host == "200.53.144.37" and cfg.port == 2347
    assert cfg.tls is True and cfg.tpdu == from_hex("6000000000")
    assert cfg.tid == "14400757" and cfg.mid == "8647574" and cfg.mcc == "5541"


# --- construcción del 0200 --------------------------------------------------
def test_build_purchase_has_f55_and_terminal():
    cfg = SwitchConfig(tid="14400757", mcc="5541")
    msg = switch.build_purchase(cfg, _card(), 1500)
    mti, fields = iso8583.parse(msg)
    assert mti == "0200"
    assert fields[41] == b"14400757"  # F41 TID
    from emvy.core import tlv

    assert tlv.parse(fields[55]).find("9F26").value == from_hex(
        "D6F5B2E0E50B0F9C"
    )  # ARQC


def test_run_purchase_dry_run():
    cfg = SwitchConfig(host="10.0.0.1", port=5000, tid="T")
    res = switch.run_purchase(cfg, _card(), 500, dry_run=True)
    assert res.request and not res.response
    assert "dry-run" in res.summary()


# --- flujo completo contra un mock TCP -------------------------------------
def test_run_purchase_against_mock_switch():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    host, port = srv.getsockname()

    approved_0210 = iso8583.build(
        "0210",
        {
            4: iso8583.bcd_amount(500),
            11: iso8583.bcd("000001"),
            39: b"00",
            41: b"14400757",
        },
    )

    def serve():
        conn, _ = srv.accept()
        n = int.from_bytes(switch._recv_n(conn, 2), "big")
        switch._recv_n(conn, n)  # lee el 0200
        conn.sendall(len(approved_0210).to_bytes(2, "big") + approved_0210)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    cfg = SwitchConfig(host=host, port=port, timeout=3.0, tid="14400757")
    res = switch.run_purchase(cfg, _card(), 500, sign_on=False)
    srv.close()
    assert res.rc == "00" and res.approved
    assert "APROBAD" in res.rc_meaning.upper()


# --- helpers de respuesta ---------------------------------------------------
def test_response_helpers():
    assert iso8583.response_meaning("51").lower().startswith("fondos")
    assert iso8583.response_field39({39: b"05"}) == "05"
    assert iso8583.response_field39({}) is None


# --- plantillas de PoC genéricas -------------------------------------------
def test_template_scaffold_loads(tmp_path):
    from emvy.poc import registry, scaffold, source_file

    pocs = tmp_path / "pocs"
    scaffold.scaffold_poc(pocs, "auth-flow", template="iso8583-purchase")
    proj = SimpleNamespace(pocs_dir=pocs, path=tmp_path)
    registry.clear()
    loaded, errors = registry.load_plugins(proj)
    assert errors == [] and "auth-flow" in loaded
    assert source_file("auth-flow") == "auth-flow.py"
    registry.clear()


def test_all_templates_scaffold_and_load(tmp_path):
    from emvy.poc import registry, templates

    pocs = tmp_path / "pocs"
    for i, name in enumerate(templates.list_templates()):
        scaffold_id = f"t{i}"
        from emvy.poc.scaffold import scaffold_poc

        scaffold_poc(pocs, scaffold_id, template=name)
    registry.clear()
    loaded, errors = registry.load_plugins(
        SimpleNamespace(pocs_dir=pocs, path=tmp_path)
    )
    assert errors == [] and len(loaded) == len(templates.list_templates())
    registry.clear()


def test_render_unknown_template_raises():
    from emvy.poc import templates

    with pytest.raises(KeyError):
        templates.render("no-existe", "x")
