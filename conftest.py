"""Hace importable el paquete `emvy` durante los tests (sin instalar)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subprocess  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_systemctl(monkeypatch):
    """`emvy.cli.main()` arranca/apaga pcscd.socket automáticamente (ver
    `emvy.integrations.pcscd`); ningún test debe tocar el systemd real de la
    máquina que corre la suite. Intercepta solo las llamadas a `systemctl`
    (simulando "inactivo", sin efecto real) y deja pasar todo lo demás — así
    no interfiere con otros usos de `subprocess.run` (arduino-cli, etc.), ni
    con los tests de `test_pcscd.py` que mockean `subprocess.run` ellos mismos
    (su propio `monkeypatch.setattr` en el cuerpo del test tiene prioridad)."""
    real_run = subprocess.run

    def guarded_run(cmd, *a, **kw):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "systemctl":
            return subprocess.CompletedProcess(cmd, 0, "inactive\n", "")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", guarded_run)
