"""Fuentes alternas de firmware (GitHub releases / URLs directas) para el
BomberCat: agregar/listar/quitar fuentes, descargar sus `.uf2` a una caché local,
listarlos y limpiarlos. Efecto de red aislado (urllib, sin dependencias extra).

- Fuente **github**: `owner/repo` → descarga los `.uf2` del último release.
- Fuente **url**: una URL directa a un `.uf2`.

Persistencia: `<config>/firmware_sources.json`. Caché: `<data>/firmware_cache/<fuente>/`.
"""

from __future__ import annotations

import json
import shutil
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


# --- red: assets + descarga -------------------------------------------------
def _get(url: str, timeout: float = 20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "EMVyController",
            "Accept": "application/vnd.github+json",
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_assets(source: Source, timeout: float = 20) -> list[tuple[str, str]]:
    """Devuelve [(nombre, url)] de los `.uf2` de la fuente."""
    if source.kind == "url":
        return [(source.ref.rsplit("/", 1)[-1], source.ref)]
    api = f"https://api.github.com/repos/{source.ref}/releases/latest"
    with _get(api, timeout=timeout) as r:
        data = json.load(r)
    return [
        (a["name"], a["browser_download_url"])
        for a in data.get("assets", [])
        if a.get("name", "").endswith(".uf2")
    ]


def download_source(
    source: Source, *, timeout: float = 90, progress=None
) -> list[Path]:
    """Descarga los `.uf2` de la fuente a la caché; devuelve las rutas."""
    dest = config.ensure_dir(cache_dir() / source.name)
    out: list[Path] = []
    for name, url in fetch_assets(source, timeout=timeout):
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
    return sorted(d.rglob("*.uf2")) if d.exists() else []


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
            for sub in sorted(d.glob("*"), reverse=True):
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
        return len(files)
    p = Path(target)
    if p.exists() and p.resolve().is_relative_to(cache_dir().resolve()):
        p.unlink()
        return 1
    return 0
