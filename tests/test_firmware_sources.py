"""Tests de fuentes alternas de firmware (GitHub/URL) y de la compilación."""

import io
import json
import subprocess
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture
def fw_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_sources_crud(fw_env):
    from emvy.integrations import firmware_sources as fs

    a = fs.add_source("owner/repo")
    b = fs.add_source("https://x.org/y/mine.uf2")
    assert a.kind == "github" and a.ref == "owner/repo"
    assert b.kind == "url" and b.name == "mine.uf2"
    # normaliza URLs de repo github → owner/repo
    c = fs.add_source("https://github.com/Electronic/Cats/tree/main")
    assert c.kind == "github" and c.ref == "Electronic/Cats"
    names = {s.name for s in fs.load_sources()}
    assert {a.name, b.name, c.name} <= names
    fs.remove_source(a.name)
    assert a.name not in {s.name for s in fs.load_sources()}


def test_download_url_source_and_clean(fw_env, monkeypatch):
    """Fuente 'url': descarga directa local (urllib), sin bombercat-tools."""
    from emvy.integrations import firmware_sources as fs

    def fake_urlopen(req, timeout=0):
        return io.BytesIO(b"UF2BYTES")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    src = fs.add_source("https://x.org/y/Mine.uf2")
    assert fs.fetch_assets(src) == [("Mine.uf2", "https://x.org/y/Mine.uf2")]
    paths = fs.download_source(src)
    assert len(paths) == 1 and paths[0].read_bytes() == b"UF2BYTES"
    assert fs.cached_firmwares() == paths

    assert fs.clean_cache(paths[0]) == 1  # borra uno
    assert fs.cached_firmwares() == []
    # limpiar todo (idempotente)
    fs.download_source(src)
    assert fs.clean_cache() == 1 and fs.cached_firmwares() == []


def test_download_github_delegates_to_bombercat_tools(fw_env, monkeypatch):
    """Fuente 'github': delega en el ReleaseCache de bombercat-tools por
    subprocess; el .uf2 baja al cache anidado por tag y clean_cache lo limpia."""
    from emvy.integrations import bombercat_tools as bt
    from emvy.integrations import firmware_sources as fs

    # No se listan assets aquí: el release lo resuelve bombercat-tools.
    src = fs.add_source("owner/repo")
    assert src.kind == "github"
    with pytest.raises(ValueError):
        fs.fetch_assets(src)

    monkeypatch.setattr(bt, "locate", lambda: fw_env)
    monkeypatch.setattr(bt, "ensure_venv", lambda root, log=None: "py")

    def fake_run(cmd, **kw):
        # emula al ReleaseCache: crea <dest>/<tag>/Foo.uf2 y devuelve su ruta.
        dest, repo = cmd[3], cmd[4]
        assert repo == "owner/repo"
        tagdir = Path(dest) / "v1.0"
        tagdir.mkdir(parents=True, exist_ok=True)
        img = tagdir / "Foo.uf2"
        img.write_bytes(b"UF2BYTES")
        return subprocess.CompletedProcess(cmd, 0, json.dumps([str(img)]), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    paths = fs.download_source(src)
    assert len(paths) == 1 and paths[0].read_bytes() == b"UF2BYTES"
    assert fs.cached_firmwares() == paths  # rglob encuentra el .uf2 anidado
    assert fs.clean_cache() == 1 and fs.cached_firmwares() == []


def test_download_github_surfaces_failure(fw_env, monkeypatch):
    from emvy.integrations import bombercat_tools as bt
    from emvy.integrations import firmware_sources as fs

    src = fs.add_source("owner/repo")
    monkeypatch.setattr(bt, "locate", lambda: fw_env)
    monkeypatch.setattr(bt, "ensure_venv", lambda root, log=None: "py")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "no release"),
    )
    with pytest.raises(RuntimeError, match="no release"):
        fs.download_source(src)


def test_list_sketches_and_compile(monkeypatch, tmp_path):
    from emvy.integrations import arduino as ard

    assert any(
        p.name == "EMVyBomberCat" for p in ard.list_sketches()
    )  # sketch del repo

    called = {}

    def fake_run(cmd, **kw):
        called["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "compiled", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    sk = tmp_path / "sk"
    sk.mkdir()
    (sk / "x.ino").write_text("void setup(){}\nvoid loop(){}")
    cp = ard.compile_sketch(sk)  # sin build.sh → arduino-cli
    assert cp.returncode == 0 and called["cmd"][0] == "arduino-cli"
    assert "--output-dir" in called["cmd"]


def test_upload_sketch_uses_picotool_not_uf2(monkeypatch, tmp_path):
    """El FQBN 'bombercat' sube por picotool (arduino-cli upload), no por .uf2:
    verifica que upload_sketch() nunca invoca el flasher de bombercat-tools."""
    from emvy.integrations import arduino as ard

    called = {}

    def fake_run(cmd, **kw):
        called["cmd"] = cmd
        called["env"] = kw.get("env")
        return subprocess.CompletedProcess(cmd, 0, "uploaded", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # sin build.sh -> arduino-cli upload directo, con puerto
    sk = tmp_path / "sk"
    sk.mkdir()
    (sk / "x.ino").write_text("void setup(){}\nvoid loop(){}")
    cp = ard.upload_sketch(sk, port="/dev/ttyACM0")
    assert cp.returncode == 0
    assert called["cmd"][:3] == ["arduino-cli", "upload", "--fqbn"]
    assert "-p" in called["cmd"] and "/dev/ttyACM0" in called["cmd"]
    assert ".uf2" not in " ".join(called["cmd"])

    # con build.sh -> lo reusa (PORT por entorno), tampoco toca .uf2
    sk2 = tmp_path / "sk2"
    sk2.mkdir()
    (sk2 / "build.sh").write_text("#!/bin/bash\necho ok\n")
    cp2 = ard.upload_sketch(sk2, port="/dev/ttyACM1")
    assert called["cmd"] == ["bash", str(sk2 / "build.sh"), "upload"]
    assert called["env"]["PORT"] == "/dev/ttyACM1"


def test_compile_and_upload_resolve_relative_sketch_dir(monkeypatch, tmp_path):
    """Regresión: compile_sketch()/upload_sketch() reciben `cwd=sketch_dir`, así
    que una ruta RELATIVA a build.sh se reinterpretaría mal (relativa al propio
    sketch_dir, no al cwd del llamador) si no se resuelve a absoluta primero."""
    from emvy.integrations import arduino as ard

    sk = tmp_path / "relsk"
    sk.mkdir()
    (sk / "build.sh").write_text("#!/bin/bash\necho ok\n")

    called = {}

    def fake_run(cmd, **kw):
        called["cmd"] = cmd
        called["cwd"] = kw.get("cwd")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    rel = "relsk"  # ruta relativa al cwd actual

    ard.compile_sketch(rel)
    assert called["cmd"][1] == str((tmp_path / "relsk" / "build.sh").resolve())

    ard.upload_sketch(rel)
    assert called["cmd"][1] == str((tmp_path / "relsk" / "build.sh").resolve())
