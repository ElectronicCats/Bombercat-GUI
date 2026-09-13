"""GUI de escritorio (PySide6/Qt) de EMVy Controller.

Frontend nativo alternativo a la TUI. Import perezoso de PySide6: `launch()`
sólo lo requiere al abrir la ventana, así el resto del paquete no depende de Qt.
"""
from __future__ import annotations


def launch(argv=None) -> int:
    from .app import run_gui
    return run_gui(argv)
