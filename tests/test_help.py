"""Modal de ayuda (?) y footer: se abre/cierra y no rompe la app."""

import asyncio

import pytest

pytest.importorskip("textual")


def test_help_modal_opens_and_closes():
    from cardsec.tui.app import EmvyApp
    from cardsec.tui.screens.help import HelpScreen

    async def scenario():
        app = EmvyApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)

    asyncio.run(scenario())


def test_help_action_is_idempotent():
    """Pulsar ? repetido no apila varias ayudas."""
    from cardsec.tui.app import EmvyApp
    from cardsec.tui.screens.help import HelpScreen

    async def scenario():
        app = EmvyApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_help()
            await pilot.pause()
            app.action_help()  # segundo intento: no debe apilar
            await pilot.pause()
            assert sum(isinstance(s, HelpScreen) for s in app.screen_stack) == 1

    asyncio.run(scenario())
