"""Punto de entrada del binario distribuido (AppImage/.exe): abre la GUI.

Los datos del usuario (proyectos, capturas) viven en el directorio XDG del sistema
(`~/.local/share/emvy`), NO dentro del binario — por eso no se empaqueta ninguno.
El firmware sí va incluido (ver EMVyController.spec) para poder compilar/flashear.
"""

import sys

from cardsec.gui.app import run_gui

if __name__ == "__main__":
    sys.exit(run_gui(sys.argv))
