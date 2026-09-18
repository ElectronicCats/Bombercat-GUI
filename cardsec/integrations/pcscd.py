"""Gestión de `pcscd.socket` (systemd) para que el backend PC/SC funcione sin
pasos manuales: `emvy` lo activa al arrancar y lo apaga al salir — **solo si
fue él quien lo activó** (si ya estaba activo por otra razón, no lo toca).

Efecto de sistema aislado (subprocess `systemctl`). En muchos entornos Linux
con polkit, un usuario de sesión activa puede start/stop unidades systemd sin
sudo; si no es el caso aquí (systemctl ausente, sin permiso, timeout…), las
funciones devuelven `False` en vez de lanzar — la herramienta sigue funcionando
igual, solo que el usuario deberá arrancar `pcscd` a mano (ver `pcsc.PCSC_HELP`).
"""

from __future__ import annotations

import shutil
import subprocess

UNIT = "pcscd.socket"
_TIMEOUT = 8.0


def available() -> bool:
    return shutil.which("systemctl") is not None


def _run(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["systemctl", *args], capture_output=True, text=True, timeout=_TIMEOUT
        )
    except Exception:
        return None


def is_active() -> bool:
    if not available():
        return False
    cp = _run("is-active", UNIT)
    return bool(cp) and cp.stdout.strip() == "active"


def start() -> bool:
    """Intenta activar `pcscd.socket`. `True` si quedó activo; nunca lanza."""
    if not available():
        return False
    cp = _run("start", UNIT)
    return bool(cp) and cp.returncode == 0


def stop() -> bool:
    """Intenta desactivar `pcscd.socket`. `True` si se pudo; nunca lanza."""
    if not available():
        return False
    cp = _run("stop", UNIT)
    return bool(cp) and cp.returncode == 0


def ensure_started() -> bool:
    """Activa `pcscd.socket` si hace falta. Devuelve `True` solo si **esta
    llamada** lo activó (para que el llamador sepa que debe apagarlo después;
    si ya estaba activo, devuelve `False` y no hay que tocarlo al salir)."""
    if is_active():
        return False
    return start()
