"""Tests del flasheo de firmware BomberCat: parseo de la lista y la pestaña TUI
(con el adaptador de subprocess mockeado, sin flashear de verdad)."""

import pytest

from cardsec.integrations import bombercat_tools as bt


def test_parse_fw_names():
    sample = (
        "╭─ banner ─╮\n"
        "│   :=-- ascii art  │\n"  # arte: se descarta
        "┃ Firmware ┃ Size ┃ Description ┃\n"  # cabecera pesada: se ignora
        "│ NFCGate                     │ 267 KB │ relay… │\n"
        "│ magspoof                    │ 100 KB │ mag    │\n"
        "│ ESP32SerialPassthroughFlash │ 176 KB │ util   │\n"
    )
    assert bt.parse_fw_names(sample) == [
        "NFCGate",
        "magspoof",
        "ESP32SerialPassthroughFlash",
    ]


def test_firmware_tab_list_and_flash(monkeypatch):
    pytest.importorskip("textual")
    import asyncio
    from pathlib import Path
    from types import SimpleNamespace

    from textual.widgets import ListView
    from cardsec.tui.app import EmvyApp

    # mockear el adaptador (sin subprocess real)
    monkeypatch.setattr(bt, "locate", lambda: Path("/vendor/bombercat-tools"))
    monkeypatch.setattr(bt, "version", lambda: "1.1.0.0")
    monkeypatch.setattr(bt, "venv_ready", lambda *a, **k: True)
    monkeypatch.setattr(bt, "fw_list_names", lambda *a, **k: ["NFCGate", "magspoof"])
    monkeypatch.setattr(
        bt,
        "flash_capture",
        lambda name, **k: SimpleNamespace(
            returncode=0, stdout=f"flashed {name}", stderr=""
        ),
    )

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_show("tab-bc")  # dispara la carga perezosa de la lista
            await app.workers.wait_for_complete()
            await pilot.pause()
            scr = app.query_one("#screen-firmware")
            assert scr._names[:2] == ["NFCGate", "magspoof"]  # release primero

            app.query_one("#fw_list", ListView).index = 0
            scr._flash()  # flashea el seleccionado (mock)
            await app.workers.wait_for_complete()
            await pilot.pause()  # sin crash

    asyncio.run(scenario())


def test_compile_and_flash_uses_upload_not_uf2_flasher(monkeypatch):
    """'Compilar y subir' debe usar arduino.upload_sketch() (picotool), NUNCA el
    flasher .uf2 de bombercat-tools — ese es solo para las imágenes oficiales."""
    pytest.importorskip("textual")
    import asyncio
    from pathlib import Path
    from types import SimpleNamespace

    from cardsec.integrations import arduino as ard
    from cardsec.tui.app import EmvyApp

    calls = {"compile": 0, "upload": 0, "flash_capture": 0}
    monkeypatch.setattr(ard, "arduino_cli_available", lambda: True)

    def fake_compile(sketch_dir, **k):
        calls["compile"] += 1
        return SimpleNamespace(returncode=0, stdout="compiled", stderr="")

    def fake_upload(sketch_dir, *, port=None, **k):
        calls["upload"] += 1
        calls["port"] = port
        return SimpleNamespace(returncode=0, stdout="uploaded", stderr="")

    def fake_flash_capture(*a, **k):
        calls["flash_capture"] += 1
        raise AssertionError("no debe llamar al flasher .uf2 para firmware propio")

    monkeypatch.setattr(ard, "compile_sketch", fake_compile)
    monkeypatch.setattr(ard, "upload_sketch", fake_upload)
    monkeypatch.setattr(
        ard, "latest_uf2", lambda *a, **k: None
    )  # este core no genera .uf2
    monkeypatch.setattr(bt, "flash_capture", fake_flash_capture)

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.bombercat_compile_ui(str(Path("/tmp/sk")), True, "/dev/ttyACM0")
            await app.workers.wait_for_complete()
            await pilot.pause()

    asyncio.run(scenario())
    assert calls["compile"] == 1
    assert calls["upload"] == 1 and calls["port"] == "/dev/ttyACM0"
    assert calls["flash_capture"] == 0
