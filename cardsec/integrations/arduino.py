"""Compilación (y flasheo) de firmware propio con arduino-cli, para poder
compilar los sketches de `firmware/` desde la TUI. Efecto de subprocess aislado.

Usa el `build.sh` del sketch si existe (instala core/libs y compila a `build/`);
si no, cae a `arduino-cli compile --output-dir build`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .. import config

DEFAULT_FQBN = "electroniccats:mbed_rp2040:bombercat"


def arduino_cli_available() -> bool:
    return shutil.which("arduino-cli") is not None


def list_sketches() -> list[Path]:
    """Carpetas bajo `firmware/` que contienen un `.ino` (sketches compilables)."""
    root = config.repo_root() / "firmware"
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and any(d.glob("*.ino")):
            out.append(d)
    return out


def compile_sketch(
    sketch_dir,
    *,
    fqbn: str = DEFAULT_FQBN,
    upload: bool = False,
    port: str | None = None,
    timeout: float = 900,
) -> subprocess.CompletedProcess:
    """Compila el sketch (y opcionalmente sube). Salida capturada."""
    # Resuelto a absoluta: el subproceso corre con cwd=sketch_dir, así que una
    # ruta relativa aquí se reinterpretaría mal (relativa al propio sketch_dir).
    sketch_dir = Path(sketch_dir).resolve()
    build_sh = sketch_dir / "build.sh"
    env = None
    if build_sh.exists():
        cmd = ["bash", str(build_sh)] + (["upload"] if upload else [])
        if port:
            import os

            env = dict(os.environ, PORT=port)
    else:
        cmd = ["arduino-cli", "compile", "--fqbn", fqbn, "--output-dir", "build", "."]
    return subprocess.run(
        cmd,
        cwd=str(sketch_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def upload_sketch(
    sketch_dir,
    *,
    fqbn: str = DEFAULT_FQBN,
    port: str | None = None,
    timeout: float = 300,
) -> subprocess.CompletedProcess:
    """Sube el sketch ya compilado a la placa.

    **No usa `.uf2`**: el FQBN `bombercat` sube por **picotool** (reset a 1200-bps
    + carga directa del `.elf`/`.bin`), gestionado por `arduino-cli upload` — es
    el mismo mecanismo que `build.sh upload`. El flasheo por `.uf2` (BOOTSEL +
    copiar a `RPI-RP2`) es el que usa `bombercat-tools` para las imágenes
    **oficiales** prebuilt; para tu propio firmware, sube por aquí.
    """
    sketch_dir = Path(sketch_dir).resolve()
    build_sh = sketch_dir / "build.sh"
    env = None
    if build_sh.exists():
        import os

        cmd = ["bash", str(build_sh), "upload"]
        env = dict(os.environ, PORT=port) if port else None
    else:
        cmd = ["arduino-cli", "upload", "--fqbn", fqbn]
        if port:
            cmd += ["-p", port]
        cmd += ["."]
    return subprocess.run(
        cmd,
        cwd=str(sketch_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def latest_uf2(sketch_dir) -> Path | None:
    """El `.uf2` más reciente producido por la compilación del sketch, si el
    core lo genera (algunos no lo hacen; usa `upload_sketch()` en ese caso)."""
    build = Path(sketch_dir) / "build"
    uf2s = (
        sorted(build.glob("*.uf2"), key=lambda p: p.stat().st_mtime, reverse=True)
        if build.exists()
        else []
    )
    return uf2s[0] if uf2s else None
