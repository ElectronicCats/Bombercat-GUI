"""Tests del adaptador de bombercat-tools (vendorizado).

Las partes offline (parseo/ubicación) siempre corren; las que ejecutan el
framework por subprocess se saltan si su venv no está listo (para no requerir
red ni bootstrap en CI)."""

import pytest

from emvy import config
from emvy.integrations import bombercat_tools as bt

_HAS_VENDOR = (config.bombercat_tools_dir() / "bombercat.py").exists()
pytestmark = pytest.mark.skipif(
    not _HAS_VENDOR, reason="bombercat-tools no vendorizado"
)


def test_locate():
    root = bt.locate()
    assert (root / "bombercat.py").exists()


def test_version():
    v = bt.version()
    assert v and v[0].isdigit()


def test_extract_json_from_noisy_output():
    text = (
        "╰─ banner rich ─╯\n"
        "ID  Port\n"
        '{"uid": "04A1B2C3", "protocol": "ISODEP"}\n'
        "ℹ hint line\n"
    )
    objs = bt._extract_json(text)
    assert objs == [{"uid": "04A1B2C3", "protocol": "ISODEP"}]


def test_extract_json_whole_document():
    assert bt._extract_json('{"a": 1}') == [{"a": 1}]


def test_extract_json_none():
    assert bt._extract_json("solo texto, sin json") == []


@pytest.mark.skipif(
    not bt.venv_ready() if _HAS_VENDOR else True,
    reason="venv de bombercat-tools no está listo",
)
def test_run_capture_help():
    cp = bt.run_capture(["--help"], timeout=60)
    assert cp.returncode == 0
    assert "flash" in cp.stdout and "relay" in cp.stdout


# --- parseo de `status` (sin `--json`: tabla rich) --------------------------
_STATUS_TABLE = (
    "                   Firmware @ /dev/ttyACM0\n"
    "┌──────────────┬───────────────────────────────────────────┐\n"
    "│ name         │ NFCGate                                   │\n"
    "│ version      │ 0.9.7                                     │\n"
    "│ detected     │ handshake (certain)                       │\n"
    "│ capabilities │ capture, config, identify, monitor, relay │\n"
    "└──────────────┴───────────────────────────────────────────┘\n"
    "ℹ Next:\n  bombercat relay status    — live relay state\n"
)


def test_parse_status_full_table():
    st = bt.parse_status(_STATUS_TABLE)
    assert st["name"] == "NFCGate"
    assert st["version"] == "0.9.7"
    assert st["detected"] == "handshake (certain)"
    assert st["capabilities"] == [
        "capture",
        "config",
        "identify",
        "monitor",
        "relay",
    ]


def test_parse_status_empty_caps_dash():
    table = (
        "┌───┬───┐\n"
        "│ name         │ MagspoofCVSAttack │\n"
        "│ capabilities │ — │\n"
        "└───┴───┘\n"
    )
    st = bt.parse_status(table)
    assert st["name"] == "MagspoofCVSAttack"
    assert st["capabilities"] == []


def test_parse_status_no_table():
    st = bt.parse_status("nothing responded on /dev/ttyACM0.\n")
    assert st["name"] == "" and st["capabilities"] == []


def test_capability_image_and_unknown():
    assert bt.image_for_capability("mifare") == "MifareClassic"
    assert bt.image_for_capability("tags") == "DetectTags"
    with pytest.raises(bt.BombercatToolsError):
        bt.image_for_capability("identify")  # sin proveedor canónico


@pytest.mark.skipif(
    not bt.venv_ready() if _HAS_VENDOR else True,
    reason="venv de bombercat-tools no está listo",
)
def test_capability_image_matches_vendor():
    """`CAPABILITY_IMAGE` no debe derivar de `requirements.CAPABILITY_PROVIDER`
    del vendor (mapeado a la imagen `.uf2`), leído por subprocess contra el venv
    aislado del vendor (sus deps: certifi/etc. no están en el venv de EMVy)."""
    import json
    import subprocess

    root = config.bombercat_tools_dir()
    script = (
        "import json;"
        "from modules.core.requirements import CAPABILITY_PROVIDER, requirement_for;"
        "print(json.dumps({c: requirement_for(c, 'x').image_name "
        "for c in CAPABILITY_PROVIDER}))"
    )
    r = subprocess.run(
        [str(bt._venv_python(root)), "-c", script],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    vendor_map = json.loads(r.stdout.strip().splitlines()[-1])
    assert vendor_map == bt.CAPABILITY_IMAGE


# ---------------------------------------------------------------------------
# magspoof: los helpers son wrappers finos del CLI del vendor. Aquí probamos
# la lógica propia (JSONL de `card list`, construcción de args) monkeypatcheando
# `run_capture`/`run_json`, sin tocar el subproceso ni el hardware.
# ---------------------------------------------------------------------------
class _CP:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_magspoof_card_list_returns_list(monkeypatch):
    # `card list --json` emite un objeto JSON por línea (JSONL).
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: _CP('{"name": "visa"}\n')
    )
    assert bt.magspoof_card_list() == [{"name": "visa"}]


def test_magspoof_card_list_empty_store(monkeypatch):
    # Un store vacío es válido → lista vacía, NO un error (a diferencia de run_json).
    monkeypatch.setattr(bt, "run_capture", lambda args, timeout=None: _CP(""))
    assert bt.magspoof_card_list() == []


def test_magspoof_card_add_builds_args(monkeypatch):
    seen = {}

    def fake(args, timeout=None):
        seen["args"] = args
        return _CP()

    monkeypatch.setattr(bt, "run_capture", fake)
    bt.magspoof_card_add("visa", t1="%B?", t2=";?", port="/dev/ttyACM0")
    assert seen["args"] == [
        "magspoof",
        "card",
        "add",
        "visa",
        "--t1",
        "%B?",
        "--t2",
        ";?",
        "-p",
        "/dev/ttyACM0",
    ]


def test_magspoof_card_add_omits_empty_tracks(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: seen.setdefault("args", args)
    )
    bt.magspoof_card_add("visa", t1="%B?")
    assert seen["args"] == ["magspoof", "card", "add", "visa", "--t1", "%B?"]


def test_magspoof_show_returns_dict(monkeypatch):
    monkeypatch.setattr(bt, "run_json", lambda args, timeout=None: {"t1": "x"})
    assert bt.magspoof_show() == {"t1": "x"}


# ---------------------------------------------------------------------------
# Mifare (MifareClassic): wrappers finos del grupo `tags mifare` del vendor.
# Probamos la construcción de args y el parseo (keys JSONL, dump dict)
# monkeypatcheando `run_capture`/`run_json`, sin subproceso ni hardware.
# ---------------------------------------------------------------------------
def test_mifare_keys_returns_list(monkeypatch):
    # `keys --json` emite un objeto JSON por clave (JSONL), como `card list`.
    monkeypatch.setattr(
        bt,
        "run_capture",
        lambda args, timeout=None: _CP(
            '{"name": "FFFFFFFFFFFF", "key": "FFFFFFFFFFFF"}\n'
            '{"name": "A0A1A2A3A4A5", "key": "A0A1A2A3A4A5"}\n'
        ),
    )
    keys = bt.mifare_keys()
    assert [k["name"] for k in keys] == ["FFFFFFFFFFFF", "A0A1A2A3A4A5"]


def test_mifare_check_builds_args(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: seen.setdefault("args", args)
    )
    bt.mifare_check("/tmp/k.keys", sectors=40, keys=["extra.dic"], port="/dev/ttyACM0")
    assert seen["args"] == [
        "tags",
        "mifare",
        "check",
        "--output-keys",
        "/tmp/k.keys",
        "--sectors",
        "40",
        "--keys",
        "extra.dic",
        "--force",
        "-p",
        "/dev/ttyACM0",
    ]


def test_mifare_dump_builds_args_and_returns_dict(monkeypatch):
    seen = {}

    def fake(args, timeout=None):
        seen["args"] = args
        return {"uid": "DEADBEEF", "sectors": [{}, {}]}

    monkeypatch.setattr(bt, "run_json", fake)
    data = bt.mifare_dump("/tmp/k.keys", "/tmp/d.json", sectors=16)
    assert data["uid"] == "DEADBEEF"
    assert seen["args"] == [
        "tags",
        "mifare",
        "dump",
        "--keys-file",
        "/tmp/k.keys",
        "--out",
        "/tmp/d.json",
        "--sectors",
        "16",
        "--json",
        "--force",
    ]


def test_mifare_restore_always_passes_yes(monkeypatch):
    # Sin TTY en el subproceso, `restore` DEBE llevar `--yes` o se colgaría
    # esperando la confirmación interactiva del bloque 0.
    seen = {}
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: seen.setdefault("args", args)
    )
    bt.mifare_restore("/tmp/d.json")
    assert seen["args"] == [
        "tags",
        "mifare",
        "restore",
        "--dump",
        "/tmp/d.json",
        "--yes",
    ]


# ---------------------------------------------------------------------------
# Relay NFCGate: `config show`/`status` parsean tablas rich de 2 columnas
# (reusan `_table_rows`, como `parse_status`); `config wifi`/`config nfcgate`/
# `run`/`stop` son wrappers finos que solo construyen args; `capture_run`
# acota una captura sin fin con el timeout de subprocess y siempre desarma.
# ---------------------------------------------------------------------------
_RELAY_CONFIG_TABLE = (
    "                   BomberCat @ /dev/ttyACM0\n"
    "┌─────────┬─────────────────┐\n"
    "│ fw      │ NFCGate         │\n"
    "│ role    │ reader          │\n"
    "│ ssid    │ MyNetwork       │\n"
    "│ server  │ 192.168.1.10    │\n"
    "│ port    │ 8080            │\n"
    "│ session │ 7               │\n"
    "│ state   │ idle            │\n"
    "└─────────┴─────────────────┘\n"
)


def test_parse_relay_config_full_table():
    cfg = bt.parse_relay_config(_RELAY_CONFIG_TABLE)
    assert cfg == {
        "fw": "NFCGate",
        "role": "reader",
        "ssid": "MyNetwork",
        "server": "192.168.1.10",
        "port": "8080",
        "session": "7",
        "state": "idle",
    }


def test_relay_config_show_returns_dict(monkeypatch):
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: _CP(_RELAY_CONFIG_TABLE)
    )
    cfg = bt.relay_config_show()
    assert cfg["ssid"] == "MyNetwork" and cfg["state"] == "idle"


_RELAY_STATUS_TABLE = (
    "                Relay status @ /dev/ttyACM0\n"
    "┌─────────────────────┬─────────┐\n"
    "│ state                │ relaying │\n"
    "│ link connected       │ yes      │\n"
    "│ peer present         │ no       │\n"
    "│ APDU pairs relayed   │ 42       │\n"
    "└─────────────────────┴─────────┘\n"
)


def test_parse_relay_status_yes_no_and_counter():
    st = bt.parse_relay_status(_RELAY_STATUS_TABLE)
    assert st == {
        "state": "relaying",
        "link_connected": True,
        "peer_present": False,
        "relayed": "42",
    }


def test_relay_config_wifi_builds_args(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: seen.setdefault("args", args)
    )
    bt.relay_config_wifi("MyNetwork", "secret", port="/dev/ttyACM0")
    assert seen["args"] == [
        "relay",
        "config",
        "wifi",
        "--ssid",
        "MyNetwork",
        "--password",
        "secret",
        "--save",
        "-p",
        "/dev/ttyACM0",
    ]


def test_relay_config_wifi_no_save(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: seen.setdefault("args", args)
    )
    bt.relay_config_wifi("MyNetwork", save=False)
    assert seen["args"] == [
        "relay",
        "config",
        "wifi",
        "--ssid",
        "MyNetwork",
        "--password",
        "",
        "--no-save",
    ]


def test_relay_config_nfcgate_builds_args(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: seen.setdefault("args", args)
    )
    bt.relay_config_nfcgate("host:1234", 7, "card", save=False)
    assert seen["args"] == [
        "relay",
        "config",
        "nfcgate",
        "--server",
        "host:1234",
        "--session",
        "7",
        "--role",
        "card",
        "--no-save",
    ]


def test_relay_run_and_stop_pass_through(monkeypatch):
    seen = []
    monkeypatch.setattr(
        bt, "run_capture", lambda args, timeout=None: seen.append(args) or _CP()
    )
    bt.relay_run(port="/dev/ttyACM0")
    bt.relay_stop(port="/dev/ttyACM0")
    assert seen == [
        ["relay", "run", "-p", "/dev/ttyACM0"],
        ["relay", "stop", "-p", "/dev/ttyACM0"],
    ]


def test_capture_run_completes_within_duration(monkeypatch):
    # El comando terminó solo (link caído) antes del plazo: sin timeout.
    calls = []

    def fake_run_capture(args, timeout=None):
        calls.append(args)
        return _CP("link ended after 3 APDU frame(s)")

    monkeypatch.setattr(bt, "run_capture", fake_run_capture)
    cp, timed_out = bt.capture_run("/tmp/out.pcap", duration=5)
    assert not timed_out
    assert cp.stdout == "link ended after 3 APDU frame(s)"
    # capture_run llama a `capture start` y, siempre, a `capture stop` (idempotente).
    assert calls == [
        ["capture", "start", "-o", "/tmp/out.pcap", "--force"],
        ["capture", "stop"],
    ]


def test_capture_run_times_out_and_always_disarms(monkeypatch):
    import subprocess

    calls = []

    def fake_run_capture(args, timeout=None):
        calls.append(args)
        if args[:2] == ["capture", "start"]:
            raise subprocess.TimeoutExpired(
                cmd=args, timeout=timeout, output="two frames so far", stderr=""
            )
        return _CP()  # capture stop

    monkeypatch.setattr(bt, "run_capture", fake_run_capture)
    cp, timed_out = bt.capture_run("/tmp/out.pcap", duration=5, port="/dev/ttyACM0")
    assert timed_out
    assert cp.stdout == "two frames so far"
    assert calls[0] == [
        "capture",
        "start",
        "-o",
        "/tmp/out.pcap",
        "--force",
        "-p",
        "/dev/ttyACM0",
    ]
    # el disarm SIEMPRE corre tras el timeout, aunque el kill saltara el
    # `finally` propio del comando del vendor.
    assert calls[1] == ["capture", "stop", "-p", "/dev/ttyACM0"]
