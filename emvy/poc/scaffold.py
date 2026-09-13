"""Generación de plantillas de plugin de PoC (`emvy poc new`)."""
from __future__ import annotations

from pathlib import Path

TEMPLATE = '''\
"""PoC: {id}

Plugin del proyecto (se carga desde <proyecto>/pocs/). Uso autorizado del
engagement. Documenta la autorización en la metadata.
"""
from emvy.poc import poc, Severity, Status
# Helpers reutilizables disponibles:
#   from emvy.payments import EmvCard, iso8583, cryptogram
#   ctx.http()  -> cliente HTTP con evidencia (solo-lectura salvo --allow-write)
#   ctx.card    -> EmvCard capturada (si se pasó --card)
#   ctx.var("nombre")  -> variable del proyecto


@poc(
    id="{id}",
    title="{title}",
    category="general",          # emv | switch | api | nfc | magstripe
    severity=Severity.MEDIUM,
    description="Describe qué prueba este PoC.",
    authorization="Prueba autorizada — <cliente/alcance>.",
)
def run(ctx):
    ctx.log("ejecutando {id}...")

    # Ejemplo (solo-lectura):
    # r = ctx.http().get(ctx.require("target_url"))
    # if r.status == 401:
    #     return ctx.result(Status.INFO, "endpoint existe (401)")

    findings = [
        ctx.finding("Ejemplo de hallazgo", Severity.LOW,
                    "reemplaza esto por la lógica real del PoC"),
    ]
    return ctx.result(Status.INFO, "PoC de ejemplo — implementa la lógica", findings)
'''


def scaffold_poc(pocs_dir: Path, poc_id: str, title: str = "",
                 template: str | None = None) -> Path:
    """Crea `<pocs_dir>/<id>.py`. Con `template`, usa una plantilla genérica
    (ver `emvy.poc.templates`); si no, la plantilla de ejemplo por defecto."""
    pocs_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in poc_id)
    path = pocs_dir / f"{safe}.py"
    if path.exists():
        raise FileExistsError(f"Ya existe {path}")
    if template:
        from .templates import render
        content = render(template, poc_id)
    else:
        content = TEMPLATE.format(id=poc_id, title=title or poc_id)
    path.write_text(content)
    return path
