"""Tests del adaptador de bombercat-tools (vendorizado).

Las partes offline (parseo/ubicación) siempre corren; las que ejecutan el
framework por subprocess se saltan si su venv no está listo (para no requerir
red ni bootstrap en CI)."""
import pytest

from emvy import config
from emvy.integrations import bombercat_tools as bt

_HAS_VENDOR = (config.bombercat_tools_dir() / "bombercat.py").exists()
pytestmark = pytest.mark.skipif(not _HAS_VENDOR, reason="bombercat-tools no vendorizado")


def test_locate():
    root = bt.locate()
    assert (root / "bombercat.py").exists()


def test_version():
    v = bt.version()
    assert v and v[0].isdigit()


def test_extract_json_from_noisy_output():
    text = (
        "╰─ banner rich ─╯\n"
        'ID  Port\n'
        '{"uid": "04A1B2C3", "protocol": "ISODEP"}\n'
        "ℹ hint line\n"
    )
    objs = bt._extract_json(text)
    assert objs == [{"uid": "04A1B2C3", "protocol": "ISODEP"}]


def test_extract_json_whole_document():
    assert bt._extract_json('{"a": 1}') == [{"a": 1}]


def test_extract_json_none():
    assert bt._extract_json("solo texto, sin json") == []


@pytest.mark.skipif(not bt.venv_ready() if _HAS_VENDOR else True,
                    reason="venv de bombercat-tools no está listo")
def test_run_capture_help():
    cp = bt.run_capture(["--help"], timeout=60)
    assert cp.returncode == 0
    assert "flash" in cp.stdout and "relay" in cp.stdout
