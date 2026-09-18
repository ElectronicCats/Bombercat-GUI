"""Framework de PoCs: runner + carga de plugins del proyecto (sin PoCs
integrados). Los PoCs específicos del cliente viven en `<proyecto>/pocs/*.py`.

Ejemplo de plugin:

    from cardsec.poc import poc, Severity, Status

    @poc(id="mi-poc", title="...", category="api", severity=Severity.HIGH,
         authorization="Prueba autorizada — cliente X")
    def run(ctx):
        r = ctx.http().get(ctx.require("target_url"))
        return ctx.result(Status.INFO, f"status {r.status}")
"""

from __future__ import annotations

from .model import (  # noqa: F401
    Finding,
    Poc,
    PocContext,
    PocError,
    PocMeta,
    PocResult,
    Severity,
    Status,
)
from .registry import (
    clear,
    get,
    list_pocs,
    load_plugins,
    poc,
    register,
    source_file,
)  # noqa: F401
from .runner import make_context, run_poc, save_result  # noqa: F401

__all__ = [
    "poc",
    "register",
    "get",
    "list_pocs",
    "load_plugins",
    "clear",
    "source_file",
    "make_context",
    "run_poc",
    "save_result",
    "Poc",
    "PocMeta",
    "PocResult",
    "PocContext",
    "Finding",
    "PocError",
    "Severity",
    "Status",
]
