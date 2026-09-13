"""Tests de la gestión de pcscd.socket (arranque/apagado automático) y su
integración en `emvy.cli.main`. `subprocess.run` va mockeado: nunca debe tocar
el pcscd real de la máquina que corre los tests."""
import subprocess

from emvy.integrations import pcscd


def _fake_run(states: dict):
    """Simula `systemctl <verb> pcscd.socket`; `states['active']` es el estado."""
    def run(cmd, **kw):
        verb = cmd[1]
        if verb == "is-active":
            out = "active" if states["active"] else "inactive"
            return subprocess.CompletedProcess(cmd, 0, out + "\n", "")
        if verb == "start":
            states["active"] = True
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if verb == "stop":
            states["active"] = False
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 1, "", "unknown verb")
    return run


def test_ensure_started_when_already_active_does_nothing(monkeypatch):
    states = {"active": True}
    monkeypatch.setattr(subprocess, "run", _fake_run(states))
    assert pcscd.is_active() is True
    started = pcscd.ensure_started()
    assert started is False           # no lo tocamos, ya estaba activo
    assert states["active"] is True   # sigue activo


def test_ensure_started_when_inactive_starts_it(monkeypatch):
    states = {"active": False}
    monkeypatch.setattr(subprocess, "run", _fake_run(states))
    started = pcscd.ensure_started()
    assert started is True
    assert states["active"] is True
    assert pcscd.is_active() is True


def test_stop_turns_it_off(monkeypatch):
    states = {"active": True}
    monkeypatch.setattr(subprocess, "run", _fake_run(states))
    assert pcscd.stop() is True
    assert states["active"] is False


def test_never_raises_when_systemctl_missing(monkeypatch):
    monkeypatch.setattr(pcscd, "available", lambda: False)
    assert pcscd.is_active() is False
    assert pcscd.start() is False
    assert pcscd.stop() is False
    assert pcscd.ensure_started() is False


def test_never_raises_on_subprocess_error(monkeypatch):
    def boom(cmd, **kw):
        raise OSError("systemctl no encontrado")
    monkeypatch.setattr(subprocess, "run", boom)
    assert pcscd.is_active() is False
    assert pcscd.start() is False
    assert pcscd.stop() is False


def test_never_raises_on_timeout(monkeypatch):
    def timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 8))
    monkeypatch.setattr(subprocess, "run", timeout)
    assert pcscd.is_active() is False
    assert pcscd.start() is False


# --- integración en emvy.cli.main ------------------------------------------
def test_cli_main_starts_and_stops_when_it_was_inactive(monkeypatch):
    from emvy import cli

    calls = []
    monkeypatch.setattr(cli.pcscd, "ensure_started", lambda: (calls.append("ensure"), True)[1])
    monkeypatch.setattr(cli.pcscd, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(cli, "build_parser", lambda: _DummyParser())

    rc = cli.main(["readers"])
    assert rc == 0
    assert calls == ["ensure", "stop"]      # arrancó y apagó, en ese orden


def test_cli_main_does_not_stop_when_it_was_already_active(monkeypatch):
    from emvy import cli

    calls = []
    monkeypatch.setattr(cli.pcscd, "ensure_started", lambda: (calls.append("ensure"), False)[1])
    monkeypatch.setattr(cli.pcscd, "stop", lambda: calls.append("stop"))
    monkeypatch.setattr(cli, "build_parser", lambda: _DummyParser())

    rc = cli.main(["readers"])
    assert rc == 0
    assert calls == ["ensure"]              # nunca llama a stop


def test_cli_main_stops_even_if_command_raises(monkeypatch):
    from emvy import cli

    calls = []
    monkeypatch.setattr(cli.pcscd, "ensure_started", lambda: (calls.append("ensure"), True)[1])
    monkeypatch.setattr(cli.pcscd, "stop", lambda: calls.append("stop"))

    class BoomParser:
        def parse_args(self, argv):
            import argparse
            ns = argparse.Namespace()
            ns.func = _raise
            return ns

    monkeypatch.setattr(cli, "build_parser", lambda: BoomParser())
    try:
        cli.main(["whatever"])
    except RuntimeError:
        pass
    assert calls == ["ensure", "stop"]      # el finally corre igual


def _raise(args):
    raise RuntimeError("boom")


class _DummyParser:
    def parse_args(self, argv):
        import argparse
        ns = argparse.Namespace()
        ns.func = lambda a: 0
        return ns
