"""Ejecución de PoCs: arma el contexto, corre el PoC de forma segura y persiste
resultado + evidencias en `<proyecto>/poc_runs/<ts>-<id>/`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .http import http_factory
from .model import Poc, PocContext, PocError, PocResult, Status


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_dir_for(project, poc_id: str) -> Path:
    base = getattr(project, "poc_runs_dir", None)
    base = base if base is not None else (project.path / "poc_runs")
    ts = _now()
    d = base / f"{ts}-{poc_id}"
    n = 2
    while d.exists():   # el timestamp es de segundos: evita colisión/sobrescritura
        d = base / f"{ts}-{poc_id}-{n}"
        n += 1
    return d


def make_context(project, *, card=None, variables=None, dry_run: bool = False,
                 allow_write: bool = False, run_dir: Path | None = None,
                 log=None) -> PocContext:
    """Arma un PocContext desde el proyecto (variables) + opciones."""
    if variables is None and project is not None:
        from ..project import store
        variables = {v.name: v.value for v in store.load_project_variables(project)}
    return PocContext(
        project=project,
        variables=variables or {},
        card=card,
        evidence_dir=run_dir or Path("."),
        dry_run=dry_run,
        allow_write=allow_write,
        http_factory=http_factory,
        logger=log,
    )


def run_poc(p: Poc, ctx: PocContext) -> PocResult:
    """Ejecuta un PoC de forma segura y devuelve su PocResult (con timing/errores)."""
    started = _now()
    ctx.evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = p.run(ctx)
        if result is None:  # el PoC no devolvió resultado explícito
            result = PocResult(poc_id=p.meta.id, status=Status.INFO)
        if isinstance(result, Status):  # conveniencia: devolver solo un estado
            result = PocResult(poc_id=p.meta.id, status=result)
    except PocError as e:
        result = PocResult(poc_id=p.meta.id, status=Status.SKIPPED,
                           summary=str(e), error=str(e))
    except Exception as e:  # noqa: BLE001  — un PoC no debe tumbar al runner
        result = PocResult(poc_id=p.meta.id, status=Status.ERROR,
                           summary=f"{type(e).__name__}: {e}", error=str(e))

    result.poc_id = p.meta.id
    result.started = started
    result.finished = _now()
    result.evidence = list(dict.fromkeys(result.evidence + ctx.evidence))
    return result


def save_result(ctx: PocContext, meta, result: PocResult) -> Path:
    """Guarda meta + result como JSON en el directorio del run."""
    ctx.evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta.to_dict(), "result": result.to_dict()}
    import json
    path = ctx.evidence_dir / "result.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path
