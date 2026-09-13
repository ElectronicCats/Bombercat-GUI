"""Tests de perfiles de terminal preconfigurados (project.profiles)."""
import pytest

from emvy.core import emvbits
from emvy.core.hexutil import from_hex
from emvy.project import env, profiles


def test_list_and_get():
    ids = {p.id for p in profiles.list_profiles()}
    assert {"contactless-kiosk", "contactless-attended", "contact-attended", "atm"} <= ids
    assert profiles.get("atm").title.lower().startswith("cajero")
    assert profiles.get("no-existe") is None


def test_apply_unknown_raises():
    with pytest.raises(ValueError):
        profiles.apply_profile([], "no-existe")


def test_apply_only_touches_its_own_aliases():
    base = env.set_var([], "amount", "000000001500")   # variable ajena al perfil
    out = profiles.apply_profile(base, "contactless-kiosk")
    assert env.get_var(out, "amount").value == "000000001500"   # intacta
    assert env.get_var(out, "terminal_type").value == "24"
    assert env.get_var(out, "ttq").value == "20000000"
    assert all(v.kind == "terminal" for v in out if v.name in ("terminal_type", "ttq"))


def test_kiosk_ttq_has_no_cvm_bits():
    p = profiles.get("contactless-kiosk")
    flags = emvbits.set_flags(emvbits.decode_ttq(from_hex(p.values["ttq"])))
    assert "CVM requerido" not in flags
    assert "EMV modo soportado" in flags


def test_attended_ttq_requires_cvm_and_online_crypto():
    p = profiles.get("contactless-attended")
    flags = emvbits.set_flags(emvbits.decode_ttq(from_hex(p.values["ttq"])))
    assert "CVM requerido" in flags and "Criptograma online requerido" in flags


def test_contact_profile_does_not_touch_ttq():
    out = profiles.apply_profile([], "contact-attended")
    assert env.get_var(out, "ttq") is None
    assert env.get_var(out, "terminal_type").value == "22"
    assert env.get_var(out, "txn_type").value == "00"


def test_atm_profile_sets_cash_withdrawal():
    out = profiles.apply_profile([], "atm")
    assert env.get_var(out, "terminal_type").value == "14"
    assert env.get_var(out, "txn_type").value == "01"


def test_reapplying_overwrites_not_duplicates():
    out = profiles.apply_profile([], "contactless-kiosk")
    out = profiles.apply_profile(out, "contactless-attended")
    matches = [v for v in out if v.name == "terminal_type"]
    assert len(matches) == 1 and matches[0].value == "22"
