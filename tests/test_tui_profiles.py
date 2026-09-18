"""Prueba headless: aplicar un perfil de terminal desde la pestaña Variables."""

import pytest

pytest.importorskip("textual")


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_apply_profile_from_variables_tab(xdg):
    import asyncio

    from textual.widgets import Select

    from cardsec.project import env, store
    from cardsec.tui.app import EmvyApp

    async def scenario():
        store.create_project("lab")
        store.set_active("lab")
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_show("tab-vars")
            await pilot.pause()
            scr = app.query_one("#screen-variables")

            sel = app.query_one("#var_profile", Select)
            sel.value = "atm"
            await pilot.pause()
            desc = str(app.query_one("#var_profile_desc").render())
            assert "retiro de efectivo" in desc.lower()

            scr._apply_profile()
            await pilot.pause()

            variables = store.load_project_variables(store.active_project())
            assert env.get_var(variables, "terminal_type").value == "14"
            assert env.get_var(variables, "txn_type").value == "01"

    asyncio.run(scenario())
