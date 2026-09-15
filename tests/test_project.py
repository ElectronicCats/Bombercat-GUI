"""Tests de variables de entorno (CRUD/encoders) y persistencia de proyectos."""

import pytest

from emvy.project import env, store
from emvy.project.model import Variable


# --- variables: CRUD puro + encoders ---------------------------------------
def test_resolve_tag_and_kind():
    assert env.resolve_tag("amount") == "9F02"
    assert env.resolve_tag("9F02") == "9F02"
    assert env.resolve_tag("target_bank") is None
    assert env.make_variable("amount", "000000000100").kind == "terminal"
    assert env.make_variable("nota", "hola").kind == "user"


def test_encode_value_text_vs_hex():
    # 9F4E (ans) -> texto; 9F02 (n) -> hex
    assert env.encode_value("9F4E", "ACME") == b"ACME"
    assert env.encode_value("9F02", "000000000100") == bytes.fromhex("000000000100")


def test_crud_and_profile():
    vs = env.default_variables()
    assert any(v.tag == "9F02" for v in vs)
    vs = env.set_var(vs, "amount", "000000001500")
    vs = env.set_var(vs, "merchant_name", "ACME REDTEAM")  # an/ans
    vs = env.set_var(vs, "target", "BancoX")  # user
    prof = env.to_terminal_profile(vs)
    assert prof["9F02"] == bytes.fromhex("000000001500")
    assert prof["9F4E"] == b"ACME REDTEAM"
    assert env.get_var(vs, "target").kind == "user"
    assert "target" not in prof  # las user no van al perfil terminal

    vs = env.del_var(vs, "target")
    assert env.get_var(vs, "target") is None


def test_set_invalid_terminal_value_raises():
    with pytest.raises(ValueError):
        # 'amount' es numérico -> exige hex; 'xyz' no es hex
        env.set_var([], "amount", "xyz")


def test_variable_serialization_roundtrip():
    v = Variable("amount", "000000000100", "terminal", "9F02", "monto")
    assert Variable.from_dict(v.to_dict()) == v


# --- store: proyectos en disco ---------------------------------------------
@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_project_lifecycle(xdg):
    p = store.create_project("lab", description="pentest", reader="0")
    assert store.project_exists("lab")
    assert [x.name for x in store.list_projects()] == ["lab"]

    # variables por defecto sembradas
    vs = store.load_project_variables(p)
    assert any(v.tag == "9F02" for v in vs)
    vs = env.set_var(vs, "amount", "000000002500")
    store.save_project_variables(p, vs)
    assert (
        env.get_var(store.load_project_variables(p), "amount").value == "000000002500"
    )

    # capturas
    store.save_capture(p, "card1", '{"atr":"3B00"}')
    assert [x.name for x in store.list_captures(p)] == ["card1.json"]

    # activo
    store.set_active("lab")
    assert store.get_active() == "lab" and store.active_project().name == "lab"

    store.delete_project("lab")
    assert not store.project_exists("lab") and store.get_active() is None


def test_invalid_project_name(xdg):
    with pytest.raises(store.ProjectError):
        store.create_project("../evil")


def test_duplicate_project(xdg):
    store.create_project("dup")
    with pytest.raises(store.ProjectError):
        store.create_project("dup")


# --- exportar / importar proyecto completo ---------------------------------
def _seed_project(name="lab-visa"):
    p = store.create_project(name, description="engagement demo")
    vs = env.set_var(store.load_project_variables(p), "amount", "000000001500")
    vs = env.set_var(vs, "target", "BancoX")
    store.save_project_variables(p, vs)
    store.save_capture(p, "cap1", '{"atr":"3B00","applications":[],"blobs":[]}')
    return p


def test_export_import_roundtrip(xdg, tmp_path):
    _seed_project()
    zip_path = store.export_project(store.open_project("lab-visa"), tmp_path / "out")
    assert zip_path.exists() and zip_path.suffix == ".zip"
    assert store.peek_archive_name(zip_path) == "lab-visa"

    store.delete_project("lab-visa")
    assert not store.project_exists("lab-visa")

    p = store.import_project(zip_path)  # nombre = el del manifest
    assert p.name == "lab-visa" and store.project_exists("lab-visa")
    vs = store.load_project_variables(p)
    assert env.get_var(vs, "amount").value == "000000001500"
    assert env.get_var(vs, "target").value == "BancoX"
    assert [x.name for x in store.list_captures(p)] == ["cap1.json"]


def test_import_rename_and_overwrite(xdg, tmp_path):
    _seed_project()
    zip_path = store.export_project(store.open_project("lab-visa"), tmp_path / "out")

    p = store.import_project(zip_path, name="lab-copy")
    assert p.name == "lab-copy"  # manifest normalizado
    assert store.open_project("lab-copy").name == "lab-copy"

    with pytest.raises(store.ProjectError):
        store.import_project(zip_path, name="lab-copy")  # ya existe
    p2 = store.import_project(zip_path, name="lab-copy", overwrite=True)
    assert p2.name == "lab-copy"


def test_export_excludes_runs(xdg, tmp_path):
    import zipfile

    p = _seed_project()
    (p.poc_runs_dir / "20260101-run").mkdir(parents=True)
    (p.poc_runs_dir / "20260101-run" / "result.json").write_text("{}")
    zip_path = store.export_project(p, tmp_path / "out", include_runs=False)
    names = zipfile.ZipFile(zip_path).namelist()
    assert not any(n.startswith("poc_runs/") for n in names)
    # con runs sí se incluye
    zip2 = store.export_project(p, tmp_path / "out2")
    assert any(n.startswith("poc_runs/") for n in zipfile.ZipFile(zip2).namelist())


def test_import_rejects_non_project(tmp_path, xdg):
    import zipfile

    bad = tmp_path / "notproj.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("readme.txt", "hola")
    with pytest.raises(store.ProjectError):
        store.import_project(bad)


# --- descubrimiento de proyectos en ruta (engagements) ---------------------
def test_engagements_dirs_env(monkeypatch, tmp_path):
    import os

    from emvy import config

    monkeypatch.setenv(
        "EMVY_ENGAGEMENTS", str(tmp_path / "a") + os.pathsep + str(tmp_path / "b")
    )
    resolved = {str(d.resolve()) for d in config.engagements_dirs()}
    assert str((tmp_path / "a").resolve()) in resolved
    assert str((tmp_path / "b").resolve()) in resolved


def test_list_path_projects_discovers_and_activates(xdg, tmp_path, monkeypatch):
    import json

    root = tmp_path / "eng"
    d = root / "acme-under-test"
    d.mkdir(parents=True)
    (d / "project.json").write_text(
        json.dumps({"name": "acme-under-test", "description": "engagement de prueba"})
    )
    monkeypatch.setenv("EMVY_ENGAGEMENTS", str(root))

    found = {p.name: p for p in store.list_path_projects()}
    assert "acme-under-test" in found  # se descubre sin estar activo
    store.set_active_path(found["acme-under-test"].path)
    assert store.active_project().name == "acme-under-test"


def test_import_rejects_zip_slip(tmp_path, xdg):
    import zipfile

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("project.json", '{"name":"x"}')
        zf.writestr("../escape.txt", "pwn")
    with pytest.raises(store.ProjectError):
        store.import_project(evil, name="x")
