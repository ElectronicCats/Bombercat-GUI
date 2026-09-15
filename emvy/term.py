"""Color ANSI para la CLI/shell (presentación, fuera del núcleo puro).

Se auto-desactiva si la salida no es un TTY o si NO_COLOR está definido.
"""

from __future__ import annotations

import os
import sys

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}


def c(text: str, *styles: str) -> str:
    """Envuelve `text` en códigos ANSI (si el color está habilitado)."""
    if not _USE_COLOR or not styles:
        return text
    prefix = "".join(_CODES.get(s, "") for s in styles)
    return f"{prefix}{text}{_CODES['reset']}"


def set_color(enabled: bool) -> None:
    global _USE_COLOR
    _USE_COLOR = enabled
