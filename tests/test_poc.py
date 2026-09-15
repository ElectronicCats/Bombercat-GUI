"""Tests del framework de PoCs: registro, plugins, runner, HTTP (dry-run/RO)."""

import types

import pytest

from emvy import poc as pk
from emvy.poc.http import PocHttp
from emvy.poc.model import PocContext, PocError


@pytest.fixture
def project(tmp_path):
    proj = types.SimpleNamespace(
        path=tmp_path,
        pocs_dir=tmp_path / "pocs",
        poc_runs_dir=tmp_path / "poc_runs",
    )
    proj.pocs_dir.mkdir()
    return proj


PLUGIN = """
from emvy.poc import poc, Severity, Status
@poc(id="demo", title="Demo", category="api", severity=Severity.HIGH, authorization="lab")
def run(ctx):
    ctx.save_evidence("nota.txt", "hola")
    tgt = ctx.var("target", "n/a")
    return ctx.result(Status.VULNERABLE, f"target={tgt}",
                      [ctx.finding("hallazgo", Severity.HIGH, "detalle")])
"""


def test_load_and_run_plugin(project):
    (project.pocs_dir / "demo.py").write_text(PLUGIN)
    pk.clear()
    loaded, errors = pk.load_plugins(project)
    assert loaded == ["demo"] and not errors

    p = pk.get("demo")
    run_dir = pk.runner.run_dir_for(project, "demo")
    ctx = pk.make_context(
        project, variables={"target": "x"}, run_dir=run_dir, dry_run=True
    )
    res = pk.run_poc(p, ctx)
    pk.save_result(ctx, p.meta, res)
    assert res.status == pk.Status.VULNERABLE
    assert res.max_severity == pk.Severity.HIGH
    assert (run_dir / "result.json").exists()
    assert (run_dir / "nota.txt").exists()


def test_broken_plugin_does_not_crash(project):
    (project.pocs_dir / "ok.py").write_text(PLUGIN)
    (project.pocs_dir / "bad.py").write_text("import nonexistent_module_xyz\n")
    pk.clear()
    loaded, errors = pk.load_plugins(project)
    assert "demo" in loaded and any("bad.py" in e for e in errors)


def test_runner_catches_exceptions(project):
    def boom(ctx):
        raise RuntimeError("kaboom")

    p = pk.Poc(meta=pk.PocMeta(id="boom"), run=boom)
    ctx = pk.make_context(None, variables={}, run_dir=project.path / "r")
    res = pk.run_poc(p, ctx)
    assert res.status == pk.Status.ERROR and "kaboom" in res.error


def test_http_readonly_guard(tmp_path):
    ctx = PocContext(evidence_dir=tmp_path, allow_write=False)
    http = PocHttp(ctx)
    with pytest.raises(PocError):
        http.post("https://example.test/x", json={"a": 1})


def test_http_dry_run_records_evidence(tmp_path):
    ctx = PocContext(evidence_dir=tmp_path, dry_run=True)
    http = PocHttp(ctx)
    resp = http.get("https://example.test/probe")
    assert resp.status == 0
    files = [p.name for p in tmp_path.iterdir()]
    assert any("req" in f for f in files) and any("DRYRUN" in f for f in files)


def test_require_missing_var():
    ctx = PocContext(variables={})
    with pytest.raises(PocError):
        ctx.require("target_url")
