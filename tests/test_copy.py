"""Copia con Ctrl+C en toda la TUI:
  - widgets de texto (Static/RichLog/Input): selección con ratón + Ctrl+C
    (nativo de Textual; se verifica el mecanismo con un arrastre simulado);
  - `CopyableDataTable`: Ctrl+C copia la fila resaltada;
  - árbol del Explorador: Ctrl+C copia el valor del nodo resaltado, cediendo a
    la selección de texto cuando la hay.
"""
import asyncio

import pytest

pytest.importorskip("textual")

from textual import events  # noqa: E402
from textual.actions import SkipAction  # noqa: E402


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def _dump():
    from emvy.session.model import CardDump
    return CardDump(applications=[{
        "aid": "A0000000031010", "scheme": "Visa", "source": "ppse", "label": "VISA",
        "aip": "2000", "afl": "08010100", "cardholder": {},
        "records": [{"sfi": 1, "record": 1, "hex": "70059F36020031"}], "get_data": {}}],
        blobs=[])


# --- selección de texto nativa (Static) -------------------------------------
def test_native_text_selection_and_copy():
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class T(App):
        def compose(self) -> ComposeResult:
            yield Static("PAN 4111111111111111 fin", id="s")

    async def scenario():
        app = T()
        async with app.run_test(size=(80, 5)) as pilot:
            await pilot.pause()
            s = app.query_one("#s", Static)
            await pilot.mouse_down(s, offset=(0, 0))
            for x in range(1, 22, 3):
                await pilot._post_mouse_events([events.MouseMove], widget=s,
                                               offset=(x, 0), button=1)
            await pilot.mouse_up(s, offset=(21, 0))
            await pilot.pause()
            assert app.screen.get_selected_text().startswith("PAN 4111")
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app._clipboard.startswith("PAN 4111")

    asyncio.run(scenario())


# --- CopyableDataTable: copiar fila -----------------------------------------
def test_datatable_copy_row(xdg):
    from emvy.tui.app import EmvyApp
    from emvy.tui.widgets.copyable import CopyableDataTable

    async def scenario():
        app = EmvyApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.query_one("#main-tabs").active = "tab-rdr"
            await pilot.pause()
            t = app.query_one("#rdr_table", CopyableDataTable)
            t.clear(columns=True)
            t.add_columns("idx", "nombre")
            t.add_row("0", "Alcor AU9540")
            t.focus()
            t.move_cursor(row=0)
            await pilot.pause()
            app._clipboard = None
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app._clipboard == "0  Alcor AU9540"

    asyncio.run(scenario())


def test_datatable_empty_skips(xdg):
    from emvy.tui.app import EmvyApp
    from emvy.tui.widgets.copyable import CopyableDataTable

    async def scenario():
        app = EmvyApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.query_one("#main-tabs").active = "tab-rdr"
            await pilot.pause()
            t = app.query_one("#rdr_table", CopyableDataTable)
            t.clear(columns=True)
            with pytest.raises(SkipAction):
                t.action_copy_row()

    asyncio.run(scenario())


# --- árbol del Explorador: copiar nodo --------------------------------------
def test_tree_node_copy(xdg):
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.query_one("#main-tabs").active = "tab-exp"
            await pilot.pause()
            exp = app.query_one("#screen-explorer")
            exp.show_dump(_dump())
            app.query_one("#exp_tree").focus()
            exp._sel = {"tag": "9F36", "value": "DEADBEEF", "ascii": "",
                        "is_hex": True, "suggest": "9F36"}
            app._clipboard = None
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert app._clipboard == "DEADBEEF"

    asyncio.run(scenario())


def test_tree_copy_skips_without_selection(xdg):
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            exp = app.query_one("#screen-explorer")
            exp._sel = None
            with pytest.raises(SkipAction):
                exp.action_copy_node()

    asyncio.run(scenario())


def test_tree_copy_defers_to_text_selection(xdg, monkeypatch):
    """Si hay selección de texto en pantalla, Ctrl+C del árbol cede (SkipAction)
    para que la copie el manejador estándar en vez del nodo."""
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            exp = app.query_one("#screen-explorer")
            exp._sel = {"tag": "9F36", "value": "DEADBEEF", "ascii": "",
                        "is_hex": True, "suggest": "9F36"}
            # simula una selección de texto activa
            monkeypatch.setattr(exp.screen, "get_selected_text", lambda: "seleccion")
            with pytest.raises(SkipAction):
                exp.action_copy_node()

    asyncio.run(scenario())