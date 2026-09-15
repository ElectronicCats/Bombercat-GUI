"""Tests del dashboard (página de inicio): el modelo puro `build_model` (máquina
de estados de 'siguiente acción' + paneles) y una prueba de humo headless de la
TUI con Textual Pilot."""

import pytest

pytest.importorskip("textual")

from emvy.tui.screens import dashboard as dash  # noqa: E402
from emvy.tui.screens.dashboard import OK, OFF, build_model  # noqa: E402


def _model(**kw):
    base = dict(
        project_name=None,
        var_count=0,
        capture_count=0,
        reader_name=None,
        reader_backend=None,
        reader_caps=None,
        card_atr=None,
        capture_apps=None,
        capture_blobs=None,
    )
    base.update(kw)
    return build_model(**base)


# --- máquina de 'siguiente acción' -----------------------------------------
def test_next_action_no_project():
    m = _model()
    assert "proyecto" in m.next_text.lower() and m.next_keys == "P"
    assert m.reader.symbol == OFF and m.card.symbol == OFF


def test_next_action_project_but_no_reader():
    m = _model(project_name="lab")
    assert "lector" in m.next_text.lower() and m.next_keys == "L"


def test_next_action_reader_but_no_card():
    m = _model(
        project_name="lab",
        reader_name="Alcor AU9540",
        reader_backend="pcsc",
        reader_caps="contact",
    )
    assert "tarjeta" in m.next_text.lower() and m.next_keys == "L"
    assert m.reader.symbol == OK and m.card.symbol == OFF


def test_next_action_card_but_no_capture():
    m = _model(
        project_name="lab",
        reader_name="Alcor",
        reader_backend="pcsc",
        reader_caps="contact",
        card_atr="3B00",
    )
    assert "captura" in m.next_text.lower() and m.next_keys == "E"
    assert m.card.symbol == OK and m.capture.symbol == OFF


def test_next_action_capture_available():
    m = _model(
        project_name="lab",
        reader_name="Alcor",
        reader_backend="pcsc",
        reader_caps="contact",
        card_atr="3B00",
        capture_apps=2,
        capture_blobs=5,
    )
    assert m.next_keys == "E / F"
    assert m.capture.symbol == OK
    assert "2 app(s)" in " ".join(m.capture.lines)


def test_project_counts_surface():
    m = _model(
        project_name="lab-visa",
        var_count=18,
        capture_count=4,
        reader_name="Alcor",
        reader_backend="pcsc",
        reader_caps="contact",
    )
    assert m.var_count == 18 and m.capture_count == 4


# --- prueba de humo headless (Textual Pilot) -------------------------------
@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_dashboard_headless_reacts_to_state(xdg):
    import asyncio

    from textual.widgets import Static

    from emvy.readers.types import Capability, DeviceInfo
    from emvy.tui.app import EmvyApp

    from emvy.project import store

    def text_of(app, sid):
        return str(app.query_one("#" + sid, Static).render()).lower()

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # arranque: sin proyecto -> pide crear proyecto
            assert "proyecto" in text_of(app, "dash-next")

            # con proyecto activo pero sin lector -> pide conectar lector
            store.create_project("lab")
            store.set_active("lab")
            app.update_status()
            await pilot.pause()
            assert "lector" in text_of(app, "dash-next")

            # simula un lector conectado con tarjeta
            app.reader_device = DeviceInfo(
                "pcsc", "Alcor AU9540", "Alcor AU9540", frozenset({Capability.CONTACT})
            )
            app.card_atr = "3B 00"
            app.update_status()
            await pilot.pause()
            assert "conectado" in text_of(app, "dash-reader")
            assert "detectada" in text_of(app, "dash-card")
            # con lector+tarjeta pero sin captura -> sugiere capturar
            assert "captura" in text_of(app, "dash-next")

    asyncio.run(scenario())


def test_dashboard_actions_headless(xdg):
    import asyncio

    from textual.widgets import Input, TabbedContent

    from emvy.project import store
    from emvy.tui.app import EmvyApp

    async def scenario():
        app = EmvyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            dash = app.query_one("#screen-dashboard")

            # crear proyecto desde el dashboard
            app.query_one("#dash-new-name", Input).value = "nuevo-eng"
            dash._new_project()
            await pilot.pause()
            assert store.project_exists("nuevo-eng")
            assert store.active_label() == "nuevo-eng"

            # crear otro -> pasa a ser el activo
            app.query_one("#dash-new-name", Input).value = "otro"
            dash._new_project()
            await pilot.pause()
            assert store.active_label() == "otro"

            # volver al primero activándolo desde 'proyectos recientes'
            entry = next(e for e in dash._recent if e[0] == "nuevo-eng")
            dash._activate(entry)
            await pilot.pause()
            assert store.active_label() == "nuevo-eng"

            # crear un proyecto ELIGIENDO la ruta (proyecto en ruta)
            import tempfile

            loc = tempfile.mkdtemp()
            app.query_one("#dash-new-name", Input).value = "eng1"
            app.query_one("#dash-new-path", Input).value = loc + "/eng1"
            dash._new_project()
            await pilot.pause()
            from pathlib import Path

            assert (Path(loc) / "eng1" / "project.json").exists()
            assert (
                store.active_project().path.resolve() == (Path(loc) / "eng1").resolve()
            )

            # acción rápida: navega a la consola APDU, embebida en Explorador
            dash._qa_console()
            await pilot.pause()
            assert app.query_one("#main-tabs", TabbedContent).active == "tab-exp"

    asyncio.run(scenario())
