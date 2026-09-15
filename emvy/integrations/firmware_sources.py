"""Fuentes alternas de firmware para el BomberCat: agregar/listar/quitar fuentes,
descargar sus `.uf2` a una caché local, listarlos y limpiarlos.

- Fuente **github**: `owner/repo` → **delega** la descarga del último release al
  `ReleaseCache` de `bombercat-tools` (`vendor/bombercat-tools`), reusando su
  descargador endurecido (verificación de checksum, límite de tamaño, stripping
  del token en redirects cross-host). Se ejecuta por **subprocess** contra el
  venv aislado del framework —igual que el resto de `bombercat_tools`— para no
  arrastrar sus dependencias (`rich`/`certifi`) al venv de EMVy.
- Fuente **url**: una URL directa a un `.uf2` (esto `bombercat-tools` no lo
  cubre, así que la descarga se hace aquí con `urllib`).

Persistencia: `<config>/firmware_sources.json`. Caché: `<data>/firmware_cache/<fuente>/`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .. import config


def sources_file() -> Path:
    return config.config_home() / "firmware_sources.json"


def cache_dir() -> Path:
    return config.data_home() / "firmware_cache"


@dataclass(frozen=True)
class Source:
    name: str
    kind: str  # "github" | "url"
    ref: str  # "owner/repo" o una URL .uf2

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "ref": self.ref}


def _detect_kind(ref: str) -> str:
    if ref.startswith(("http://", "https://")) and ref.lower().endswith(".uf2"):
        return "url"
    if ref.startswith(("http://", "https://")):
        # URL de repo github → normalizamos a owner/repo
        return "github" if "github.com" in ref else "url"
    return "github"


def _normalize_ref(ref: str, kind: str) -> str:
    if kind == "github" and "github.com" in ref:
        parts = [p for p in ref.split("github.com/", 1)[-1].split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return ref


# --- CRUD de fuentes --------------------------------------------------------
def load_sources() -> list[Source]:
    f = sources_file()
    if not f.exists():
        return []
    try:
        return [Source(**d) for d in json.loads(f.read_text())]
    except Exception:
        return []


def save_sources(sources: list[Source]) -> None:
    config.ensure_dir(sources_file().parent)
    sources_file().write_text(json.dumps([s.to_dict() for s in sources], indent=2))


def add_source(ref: str, name: str | None = None) -> Source:
    ref = ref.strip()
    if not ref:
        raise ValueError("indica un owner/repo o una URL .uf2")
    kind = _detect_kind(ref)
    ref = _normalize_ref(ref, kind)
    name = name or (ref.split("/")[-1] if kind == "url" else ref.replace("/", "_"))
    sources = [s for s in load_sources() if s.name != name]
    src = Source(name=name, kind=kind, ref=ref)
    sources.append(src)
    save_sources(sources)
    return src


def remove_source(name: str) -> None:
    save_sources([s for s in load_sources() if s.name != name])


# --- descarga: url local (urllib) / github delegado a bombercat-tools -------
def _get(url: str, timeout: float = 20):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "EMVyController"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_assets(source: Source) -> list[tuple[str, str]]:
    """Assets `.uf2` de una fuente **url** como `[(nombre, url)]`.

    Las fuentes **github** ya no listan assets aquí: su release lo resuelve y
    descarga `bombercat-tools` (`ReleaseCache`) en `download_source`.
    """
    if source.kind == "url":
        return [(source.ref.rsplit("/", 1)[-1], source.ref)]
    raise ValueError(
        "fetch_assets solo aplica a fuentes 'url'; para 'github' usa download_source"
    )


# Se ejecuta en el intérprete del venv de bombercat-tools (cwd = su checkout),
# así que `modules` es importable y `ReleaseCache` corre con sus propias deps.
# Argumentos: <root-de-caché> <owner/repo>. Imprime en JSON las rutas .uf2.
_RELEASE_SNIPPET = (
    "import json,sys;"
    "from modules.firmware.releases import ReleaseCache;"
    "c=ReleaseCache(root=sys.argv[1], repo=sys.argv[2]);"
    "c.refresh(force=True);"
    "print(json.dumps([str(i.path) for i in c.images()]))"
)


def _download_github(source: Source, *, timeout: float, progress=None) -> list[Path]:
    """Descarga el último release de `source.ref` delegando en `bombercat-tools`.

    Reusa `ReleaseCache` (checksum + límites + redirect-auth-stripping) por
    subprocess contra su venv aislado; devuelve las rutas `.uf2` cacheadas.
    """
    from . import bombercat_tools as bt

    root = bt.locate()
    py = bt.ensure_venv(root, log=progress)
    dest = config.ensure_dir(cache_dir() / source.name)
    if progress:
        progress(f"descargando release de {source.ref} (bombercat-tools)…")
    cp = subprocess.run(
        [str(py), "-c", _RELEASE_SNIPPET, str(dest), source.ref],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if cp.returncode != 0:
        detail = (cp.stderr.strip() or cp.stdout.strip() or "sin detalle")[:400]
        raise RuntimeError(f"no se pudo descargar el release de {source.ref}: {detail}")
    return [Path(p) for p in json.loads(cp.stdout.strip().splitlines()[-1])]


def download_source(
    source: Source, *, timeout: float = 120, progress=None
) -> list[Path]:
    """Descarga los `.uf2` de la fuente a la caché; devuelve las rutas."""
    if source.kind == "github":
        return _download_github(source, timeout=timeout, progress=progress)
    dest = config.ensure_dir(cache_dir() / source.name)
    out: list[Path] = []
    for name, url in fetch_assets(source):
        target = dest / name
        if progress:
            progress(f"descargando {name}…")
        with _get(url, timeout=timeout) as r, open(target, "wb") as f:
            shutil.copyfileobj(r, f)
        out.append(target)
    return out


# --- caché ------------------------------------------------------------------
def cached_firmwares() -> list[Path]:
    d = cache_dir()
    # `is_file()`: una fuente url se cachea en un dir con el nombre del asset
    # (p.ej. `Mine.uf2/`), que rglob("*.uf2") también casaría como si fuera fw.
    return sorted(p for p in d.rglob("*.uf2") if p.is_file()) if d.exists() else []


def clean_cache(target: str | Path | None = None) -> int:
    """Borra la caché completa (target=None) o un `.uf2` concreto. Devuelve
    cuántos archivos se eliminaron."""
    if target is None:
        files = cached_firmwares()
        for f in files:
            f.unlink(missing_ok=True)
        # limpia subdirectorios vacíos
        d = cache_dir()
        if d.exists():
            for sub in sorted(d.rglob("*"), reverse=True):
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
        return len(files)
    p = Path(target)
    if p.exists() and p.resolve().is_relative_to(cache_dir().resolve()):
        p.unlink()
        return 1
    return 0
