"""Tests del panel PoC: IDE integrado (crear/editar/eliminar) y ejecución con
opciones (fuente de tarjeta, dry-run). Headless con Textual Pilot."""

import pytest

pytest.importorskip("textual")


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_poc_ide_lifecycle(xdg):
    import asyncio

    from textual.widgets import Input, TextArea

    from emvy.project import store
    from emvy.tui.app import EmvyApp

    async def scenario():
        store.create_project("lab")
        store.set_active("lab")
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_show("tab-poc")
            await pilot.pause()
            scr = app.query_one("#screen-pocs")
            proj = store.active_project()

            # crear un PoC nuevo desde el editor -> queda abierto y lista el archivo
            app.query_one("#poc_newid", Input).value = "demo1"
            scr._new()
            await pilot.pause()
            assert (proj.pocs_dir / "demo1.py").exists()
            assert scr._open_file == "demo1.py"
            assert scr._run_target == "demo1"  # PoC objetivo mapeado
            assert "demo1.py" in scr._files
            assert "demo1" in app.query_one("#poc_editor", TextArea).text

            # seleccionar el archivo en el explorador lo abre en el editor
            scr._open_file = None
            scr._open("demo1.py")
            await pilot.pause()
            assert scr._open_file == "demo1.py"

            # editar y guardar
            ta = app.query_one("#poc_editor", TextArea)
            ta.text = ta.text + "\n# EDITADO_MARKER\n"
            scr._save()
            await pilot.pause()
            assert "EDITADO_MARKER" in (proj.pocs_dir / "demo1.py").read_text()

            # eliminar el archivo abierto
            scr._delete()
            await pilot.pause()
            assert not (proj.pocs_dir / "demo1.py").exists()
            assert scr._open_file is None

    asyncio.run(scenario())


def test_poc_run_dry_run_creates_run(xdg):
    import asyncio

    from emvy.poc.scaffold import scaffold_poc
    from emvy.project import store
    from emvy.tui.app import EmvyApp

    async def scenario():
        proj = store.create_project("lab")
        store.set_active("lab")
        scaffold_poc(proj.pocs_dir, "demo-poc")  # PoC ejecutable (INFO)
        store.save_capture(proj, "cap1", '{"atr":"3B00","applications":[],"blobs":[]}')
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # ejecutar sin tarjeta, dry-run
            app.run_poc_ui("demo-poc", card_source="none", dry_run=True)
            await app.workers.wait_for_complete()
            await pilot.pause()
            runs = store.list_poc_runs(store.active_project())
            assert runs, "debería registrarse un run"
            assert (runs[0] / "result.json").exists()

            # ejecutar con captura guardada (resuelve el archivo sin reventar)
            app.run_poc_ui(
                "demo-poc", card_source="saved", capture_name="cap1.json", dry_run=True
            )
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert len(store.list_poc_runs(store.active_project())) >= 2

    asyncio.run(scenario())
