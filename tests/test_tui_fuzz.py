"""Pruebas headless de la pestaña Fuzzing: generar plantillas, escribir en
tarjeta (fake transceiver) y magspoof (fake serial)."""

import pytest

pytest.importorskip("textual")


def test_fuzz_tab_generate_and_write():
    import asyncio

    from textual.widgets import Input, Select

    from emvy.core.apdu import Response
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_show("tab-fuzz")
            await pilot.pause()
            scr = app.query_one("#screen-fuzz")

            # generar plantilla de banda -> campos poblados
            app.query_one("#fz_track_tpl", Select).value = "bad-luhn"
            scr._gen_track()
            await pilot.pause()
            t1 = app.query_one("#fz_track1", Input).value
            assert t1.startswith("%B") and t1.endswith("?")

            # generar plantilla EMV -> hex poblado
            app.query_one("#fz_card_tpl", Select).value = "no-cvm"
            scr._gen_card()
            await pilot.pause()
            hexval = app.query_one("#fz_card_hex", Input).value
            assert hexval and all(c in "0123456789ABCDEFabcdef" for c in hexval)

            # escribir: conecta un lector fake y dispara write_card_ui
            class FakeReader:
                transceive = staticmethod(lambda a: Response(b"", 0x90, 0x00))
                atr = None

            app.reader = FakeReader()
            scr._card_write()
            await app.workers.wait_for_complete()
            await pilot.pause()  # no revienta; log recibido en ambas pestañas

    asyncio.run(scenario())


def test_fuzz_tab_magspoof(monkeypatch):
    import asyncio
    import sys

    sys.path.insert(0, "tests")
    import fakeserial
    from emvy.tui.app import EmvyApp

    fakeserial.install()
    try:

        async def scenario():
            app = EmvyApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_show("tab-fuzz")
                await pilot.pause()
                scr = app.query_one("#screen-fuzz")
                scr._track_send()
                await app.workers.wait_for_complete()
                await pilot.pause()

        asyncio.run(scenario())
    finally:
        fakeserial.uninstall()


def test_fuzz_tab_ndef(monkeypatch):
    import asyncio
    import sys

    sys.path.insert(0, "tests")
    import fakeserial
    from textual.widgets import Input, Select
    from emvy.tui.app import EmvyApp

    fakeserial.install()
    try:

        async def scenario():
            app = EmvyApp()
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_show("tab-fuzz")
                await pilot.pause()
                scr = app.query_one("#screen-fuzz")
                # generar plantilla NDEF -> hex poblado
                app.query_one("#fz_ndef_tpl", Select).value = "invalid-tnf"
                scr._gen_ndef()
                await pilot.pause()
                hexval = app.query_one("#fz_ndef_hex", Input).value
                assert hexval and all(ch in "0123456789ABCDEFabcdef" for ch in hexval)
                # emular -> worker con fakeserial (corre hasta STOP, no auto-DONE)
                scr._ndef_emit()
                await pilot.pause()
                # Detener: señala al worker que mande STOP -> el worker termina
                scr._ndef_stop()
                await app.workers.wait_for_complete()
                await pilot.pause()
                # emular tarjeta EMV (perfila terminal) + detener
                scr._emv_emit()
                await pilot.pause()
                scr._ndef_stop()
                await app.workers.wait_for_complete()
                await pilot.pause()
                # Reboot: worker aparte que manda REBOOT (fakeserial responde)
                scr._ndef_reboot()
                await app.workers.wait_for_complete()
                await pilot.pause()

        asyncio.run(scenario())
    finally:
        fakeserial.uninstall()
