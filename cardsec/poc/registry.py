"""Registro de PoCs y carga de plugins del proyecto.

Los PoCs se declaran con el decorador `@poc(...)`. El core no trae PoCs
integrados: se cargan como plugins desde `<proyecto>/pocs/*.py` con
`load_plugins(project)`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .model import Poc, PocMeta, Severity

_REGISTRY: dict[str, Poc] = {}
_SOURCES: dict[str, str] = {}  # poc_id -> archivo fuente (basename)


def poc(
    id: str,
    *,
    title: str = "",
    category: str = "general",
    severity: Severity | str = Severity.INFO,
    description: str = "",
    authorization: str = "",
    tags=(),
):
    """Decorador para registrar un PoC. La función decorada es `run(ctx)`."""
    sev = severity if isinstance(severity, Severity) else Severity(str(severity))
    meta = PocMeta(
        id=id,
        title=title or id,
        category=category,
        severity=sev,
        description=description,
        authorization=authorization,
        tags=tuple(tags),
    )

    def wrap(fn):
        register(Poc(meta=meta, run=fn))
        return fn

    return wrap


def register(p: Poc) -> None:
    _REGISTRY[p.meta.id] = p


def get(poc_id: str) -> Poc | None:
    return _REGISTRY.get(poc_id)


def list_pocs() -> list[Poc]:
    return sorted(_REGISTRY.values(), key=lambda p: p.meta.id)


def clear() -> None:
    _REGISTRY.clear()
    _SOURCES.clear()


def source_file(poc_id: str) -> str | None:
    """Archivo (basename) donde se registró `poc_id`, si se cargó como plugin."""
    return _SOURCES.get(poc_id)


def load_plugins(project) -> tuple[list[str], list[str]]:
    """Importa `<proyecto>/pocs/*.py` (cada uno registra sus PoCs con @poc).

    Devuelve (ids_cargados, errores). No aborta si un plugin falla."""
    loaded: list[str] = []
    errors: list[str] = []
    pocs_dir = _pocs_dir(project)
    if not pocs_dir.exists():
        return loaded, errors
    for path in sorted(pocs_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        before = set(_REGISTRY)
        try:
            _import_file(path)
        except Exception as e:  # un plugin roto no tumba a los demás
            errors.append(f"{path.name}: {type(e).__name__}: {e}")
            continue
        new_ids = sorted(set(_REGISTRY) - before)
        for pid in new_ids:
            _SOURCES[pid] = path.name
        loaded.extend(new_ids)
    return loaded, errors


def _pocs_dir(project) -> Path:
    if project is None:
        return Path("pocs")
    return getattr(project, "pocs_dir", project.path / "pocs")


def _import_file(path: Path) -> None:
    mod_name = f"cardsec_poc_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
