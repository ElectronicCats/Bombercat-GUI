"""Tests del Explorador: copiar/asignar valores TLV a variables de entorno.

Prueba de humo headless (Textual Pilot) + la lógica de asignación (codificación
correcta según el tag destino)."""

import pytest

pytest.importorskip("textual")


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def _fake_dump():
    from emvy.session.model import CardDump

    return CardDump(
        atr="3B00",
        reader="test",
        applications=[
            {
                "aid": "A0000000031010",
                "scheme": "Visa",
                "source": "ppse",
                "label": "VISA",
                "cardholder": {"pan": "4111111111111111"},
                "aip": "2000",
                "afl": "08010100",
                "records": [
                    {"sfi": 1, "record": 1, "hex": "70059F36020031"}
                ],  # 9F36=0031
                "get_data": {"9F17": "03"},
            }
        ],
        blobs=[
            {"source": "A0000000031010:FCI", "hex": "6F06840456495341"}
        ],  # 84="VISA"
    )


def _collect(node, out):
    if isinstance(node.data, dict):
        out.append(node.data)
    for ch in node.children:
        _collect(ch, out)


def test_explorer_copy_and_assign(xdg):
    import asyncio

    from textual.widgets import Checkbox, Input, Tree

    from emvy.project import env, store
    from emvy.tui.app import EmvyApp

    async def scenario():
        store.create_project("lab")
        store.set_active("lab")
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            exp = app.query_one("#screen-explorer")
            exp.show_dump(_fake_dump())
            await pilot.pause()

            # los nodos llevan datos estructurados (tag/valor) para copiar/asignar
            datas: list = []
            _collect(app.query_one("#exp_tree", Tree).root, datas)
            tags = {d["tag"] for d in datas}
            assert (
                "9F36" in tags and "9F17" in tags and "82" in tags
            )  # TLV, GETDATA, AIP

            def active_vars():
                return store.load_project_variables(store.active_project())

            # 1) tag hex -> variable terminal (valor hex tal cual)
            exp._sel = {
                "tag": "9F36",
                "value": "0031",
                "is_hex": True,
                "suggest": "9F36",
            }
            exp._assign()
            await pilot.pause()
            v = env.get_var(active_vars(), "9F36")
            assert v and v.kind == "terminal" and v.value == "0031"

            # 2) valor hex ASCII -> tag an/ans -> se guarda como TEXTO
            exp._sel = {
                "tag": "5F20",
                "value": "4A4F484E",
                "is_hex": True,
                "suggest": "5F20",
            }
            exp._assign()
            await pilot.pause()
            assert env.get_var(active_vars(), "5F20").value == "JOHN"

            # 3) forzar variable libre (user) con nombre propio
            app.query_one("#exp_varname", Input).value = "mi_pan"
            app.query_one("#exp_varuser", Checkbox).value = True
            exp._sel = {
                "tag": None,
                "value": "4111111111111111",
                "is_hex": False,
                "suggest": "pan",
            }
            exp._assign()
            await pilot.pause()
            v = env.get_var(active_vars(), "mi_pan")
            assert v and v.kind == "user" and v.value == "4111111111111111"

            # 4) asignar el ASCII (no el hex) a un tag an/ans -> texto "VISA"
            app.query_one("#exp_varname", Input).value = "50"
            app.query_one("#exp_varuser", Checkbox).value = False
            app.query_one("#exp_varascii", Checkbox).value = True
            exp._sel = {
                "tag": "50",
                "value": "56495341",
                "ascii": "VISA",
                "is_hex": True,
                "suggest": "50",
            }
            exp._assign()
            await pilot.pause()
            assert env.get_var(active_vars(), "50").value == "VISA"

            # 5) copiar no revienta (portapapeles best-effort)
            exp._sel = {
                "tag": "9F36",
                "value": "0031",
                "ascii": "",
                "is_hex": True,
                "suggest": "9F36",
            }
            exp._copy_value()
            exp._copy_tagvalue()

    asyncio.run(scenario())


def test_explorer_analyze_button(xdg):
    import asyncio

    from textual.widgets import Tree

    from emvy.project import store
    from emvy.session.model import CardDump
    from emvy.tui.app import EmvyApp

    rec = "7012" + "82027C00" + "8E0C" + "00000000000000001F000103"
    dump = CardDump(
        applications=[
            {
                "aid": "A0000000031010",
                "scheme": "Visa",
                "source": "ppse",
                "label": "lab",
                "aip": "7C00",
                "afl": "08010100",
                "records": [{"sfi": 1, "record": 1, "hex": rec}],
                "get_data": {
                    "90": "AA" * 96,
                    "8F": "05",
                    "9F32": "03",
                    "93": "BB" * 96,
                },
            }
        ],
        blobs=[],
    )

    async def scenario():
        store.create_project("lab")
        store.set_active("lab")
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            exp = app.query_one("#screen-explorer")
            app.last_dump = dump
            exp._analyze()
            await pilot.pause()

            labels: list[str] = []

            def collect(n):
                labels.append(str(n.label))
                for ch in n.children:
                    collect(ch)

            collect(app.query_one("#exp_tree", Tree).root)
            assert any("ANÁLISIS" in s for s in labels)
            assert any("Sin CVM" in s for s in labels)  # hallazgo esperado

    asyncio.run(scenario())


def test_explorer_save_destinations(xdg, tmp_path):
    import asyncio

    from textual.widgets import Input, Select

    from emvy.project import store
    from emvy.tui.app import EmvyApp

    async def scenario():
        store.create_project("a")
        store.create_project("b")
        store.set_active("a")
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            exp = app.query_one("#screen-explorer")
            app.last_dump = _fake_dump()
            exp.reload()  # repuebla los destinos
            await pilot.pause()

            # 1) guardar en un ARCHIVO (elige la ruta)
            fpath = tmp_path / "out" / "mycap.json"
            app.query_one("#exp_dest", Select).value = "file"
            app.query_one("#exp_savename", Input).value = str(fpath)
            exp._save()
            await pilot.pause()
            assert fpath.exists()

            # 2) guardar en OTRO proyecto (no el activo)
            app.query_one("#exp_dest", Select).value = "proj:b"
            app.query_one("#exp_savename", Input).value = "cap_en_b"
            exp._save()
            await pilot.pause()
            assert [p.name for p in store.list_captures(store.open_project("b"))] == [
                "cap_en_b.json"
            ]

    asyncio.run(scenario())


def test_explorer_save_capture_to_project(xdg):
    import asyncio

    from emvy.project import store
    from emvy.tui.app import EmvyApp
    from emvy.tui.screens.explorer import ExplorerScreen

    async def scenario():
        store.create_project("lab")
        store.set_active("lab")
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            exp = app.query_one("#screen-explorer", ExplorerScreen)

            # sin captura -> no guarda, no revienta
            exp._save()
            await pilot.pause()
            assert store.list_captures(store.active_project()) == []

            # con captura -> se guarda con nombre dado
            app.last_dump = _fake_dump()
            from textual.widgets import Input

            app.query_one("#exp_savename", Input).value = "tarjeta1"
            exp._save()
            await pilot.pause()
            caps = [p.name for p in store.list_captures(store.active_project())]
            assert caps == ["tarjeta1.json"]

    asyncio.run(scenario())


def test_explorer_assign_requires_project(xdg):
    import asyncio

    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            exp = app.query_one("#screen-explorer")
            exp._sel = {
                "tag": "9F36",
                "value": "0031",
                "is_hex": True,
                "suggest": "9F36",
            }
            exp._assign()  # sin proyecto activo -> avisa, no revienta
            await pilot.pause()

    asyncio.run(scenario())


def test_raw_button_uses_nfc_mode_for_bombercat(xdg):
    """'Dump crudo' con un BomberCat conectado debe usar mode='nfc' (barrido
    corto) en vez de raw=True (barrido completo, más propenso a perder el
    campo NFC de una tarjeta sostenida a mano)."""
    import asyncio

    from emvy.readers.types import DeviceInfo
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            calls = []
            app.capture_card_ui = lambda **kw: calls.append(kw)
            app.reader_device = DeviceInfo(
                backend="bombercat", id="x", name="BomberCat"
            )
            exp = app.query_one("#screen-explorer")
            exp._raw()
            assert calls == [{"mode": "nfc"}]

    asyncio.run(scenario())


def test_raw_button_uses_raw_flag_for_other_backends(xdg):
    import asyncio

    from emvy.readers.types import DeviceInfo
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            calls = []
            app.capture_card_ui = lambda **kw: calls.append(kw)
            app.reader_device = DeviceInfo(backend="pcsc", id="x", name="Lector")
            exp = app.query_one("#screen-explorer")
            exp._raw()
            assert calls == [{"raw": True}]

    asyncio.run(scenario())


def test_console_wire_and_banner_headless(xdg):
    """La consola en vivo del Explorador acepta eventos de transporte (serie
    del BomberCat) y banners de conexión sin reventar."""
    import asyncio

    from emvy.readers.types import WireEvent
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            con = app.query_one("#screen-console")
            con.banner("conectando: BomberCat [bombercat]")
            con.wire_log(WireEvent("tx", "PING", "serial"))
            con.wire_log(WireEvent("rx", "PONG", "serial"))
            con.wire_log(WireEvent("rx", "ERR:NOCARD", "serial"))
            con.wire_log(WireEvent("info", "nota", "serial"))
            # y la app enruta on_wire a la consola sin lanzar
            app._on_reader_wire(WireEvent("tx", "WAIT 30000", "serial"))
            await pilot.pause()

    asyncio.run(scenario())


def test_on_dump_warns_when_bombercat_capture_empty(xdg):
    """Una captura vacía por BomberCat (tarjeta perdida a media lectura) debe
    avisar con un mensaje explicativo, no un silencioso '0 apps, 0 blobs'."""
    import asyncio

    from emvy.readers.types import DeviceInfo
    from emvy.session.model import CardDump
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.reader_device = DeviceInfo(
                backend="bombercat", id="x", name="BomberCat"
            )
            notices = []
            app.notify = lambda msg, **kw: notices.append((msg, kw.get("severity")))

            app._on_dump(CardDump(applications=[], blobs=[]))
            assert notices and notices[-1][1] == "warning"
            assert "perdió" in notices[-1][0] or "movió" in notices[-1][0]

            notices.clear()
            app._on_dump(CardDump(applications=[{"aid": "X"}], blobs=[]))
            assert notices[-1][1] != "warning"

    asyncio.run(scenario())
