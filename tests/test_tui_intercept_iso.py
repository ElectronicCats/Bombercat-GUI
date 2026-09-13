"""Pruebas de humo (headless) de las pestañas Intercept e ISO 8583, y del
cableado del interceptor en la app (active_send)."""
import pytest

pytest.importorskip("textual")


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_intercept_tab_and_active_send(xdg):
    import asyncio

    from textual.widgets import Checkbox, TextArea

    from emvy.core import intercept as ic
    from emvy.core import tlv
    from emvy.core.apdu import APDU, Response
    from emvy.core.hexutil import from_hex
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_show("tab-int")
            await pilot.pause()
            scr = app.query_one("#screen-intercept")

            app.query_one("#ic_rules", TextArea).text = (
                "resp set-tag 82 3900\nresp set-sw 9000")
            scr._apply()
            assert len(app.intercept_rules) == 2

            app.query_one("#ic_active", Checkbox).value = True   # dispara Changed
            await pilot.pause()
            assert app.intercept_active is True

            # el log no revienta con un Exchange
            ex = ic.Exchange(APDU(0, 0xA4, 4, 0), APDU(0, 0xA4, 4, 0),
                             Response(b"", 0x90, 0), Response(b"", 0x90, 0), ["nota"])
            scr.log_exchange(ex)

            # active_send() envuelve el transceiver con las reglas
            class FakeReader:
                transceive = staticmethod(
                    lambda a: Response(tlv.encode([tlv.tlv("82", from_hex("2000"))]), 0x69, 0x85))
                atr = None
            app.reader = FakeReader()
            resp = app.active_send()(APDU(0x80, 0xA8, 0, 0, from_hex("8300")))
            assert tlv.parse(resp.data).find("82").value == from_hex("3900")
            assert resp.sw == 0x9000

    asyncio.run(scenario())


def test_iso8583_tab_build(xdg):
    import asyncio

    from textual.widgets import Input

    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_tool("tool-iso")            # Consola → sub-pestaña ISO 8583
            await pilot.pause()
            scr = app.query_one("#screen-iso8583")

            app.query_one("#iso_mti", Input).value = "0200"
            app.query_one("#iso_de", Input).value = "4"
            app.query_one("#iso_val", Input).value = "000000001500"
            scr._set()
            await pilot.pause()
            assert 4 in scr._fields

            scr._build()
            await pilot.pause()
            assert scr._built is not None and scr._built[:2].hex() == "0200"

    asyncio.run(scenario())
