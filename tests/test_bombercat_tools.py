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
