"""Tests del análisis de seguridad EMV: bits (AIP/AUC/TTQ), CVM, ODA (inventario
+ heurística) y recuperación RSA del certificado del emisor (auto-consistente)."""

import hashlib
import random

from emvy.core import analyze, cvm, emvbits, oda, tlv
from emvy.core.hexutil import from_hex, to_hex


# --- bits -------------------------------------------------------------------
def test_decode_aip_flags():
    # 0x7C00: SDA+DDA+CVM+riesgo+auth emisor (bits 7..3)
    flags = emvbits.set_flags(emvbits.decode_aip(from_hex("7C00")))
    assert "SDA soportado" in flags and "DDA soportado" in flags
    assert "CDA soportado" not in flags


def test_decode_auc_flags():
    flags = emvbits.set_flags(emvbits.decode_auc(from_hex("FF00")))
    assert "Válida en cajeros (ATM)" in flags
    assert "Válida para efectivo doméstico" in flags


# --- CVM --------------------------------------------------------------------
def test_cvm_parse_and_risks():
    # X=0, Y=0, reglas: 1F/00 (no CVM siempre), 01/03 (PIN claro si soporta), 1E/03 (firma)
    data = from_hex("00000000" "00000000" "1F00" "0103" "1E03")
    lst = cvm.parse_cvm_list(data)
    assert lst and len(lst.rules) == 3
    assert lst.rules[0].code == 0x1F and lst.rules[0].condition == 0x00
    assert lst.rules[1].code == 0x01
    risks = lst.risks()
    assert any("Sin CVM" in r for r in risks)
    assert any("PIN en claro" in r for r in risks)
    assert any("Firma" in r for r in risks)


def test_cvm_apply_next_bit():
    # 0x41 -> code 0x01, bit 0x40 set (aplicar siguiente si falla)
    lst = cvm.parse_cvm_list(from_hex("0000000000000000" "4100"))
    assert lst.rules[0].apply_next_if_fails is True


# --- ODA inventario + claves débiles ----------------------------------------
def _tlvlist(pairs):
    lst = tlv.TLVList()
    for tag, hexval in pairs:
        lst.append(tlv.tlv(tag, from_hex(hexval)))
    return lst


def test_oda_inventory_sda_only():
    tlvs = _tlvlist(
        [
            ("82", "4000"),  # AIP: solo SDA (bit 7)
            ("8F", "05"),  # CA index
            ("90", "AA" * 64),  # cert emisor (512 bits CA)
            ("9F32", "03"),  # exponente emisor
            ("93", "BB" * 64),  # SSAD
        ]
    )
    rep = oda.oda_report(tlvs)
    assert rep.methods_supported == ["SDA"]
    assert rep.sda_ready and not rep.dda_ready
    assert rep.ca_key_bits == 512
    assert any("DÉBIL" in n for n in rep.notes)  # 512 < 1024
    assert any("Solo SDA" in n for n in rep.notes)


# --- recuperación RSA del certificado del emisor ----------------------------
def _is_prime(n, rng, k=20):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(k):
        a = rng.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits, rng):
    while True:
        c = rng.getrandbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if c % 3 == 2 and _is_prime(c, rng):  # p%3==2 => gcd(3, p-1)=1 (exp=3)
            return c


def _make_ca(bits=512):
    rng = random.Random(20260904)
    p, q = _gen_prime(bits // 2, rng), _gen_prime(bits // 2, rng)
    n = p * q
    e = 3
    d = pow(e, -1, (p - 1) * (q - 1))
    n_bytes = n.to_bytes(bits // 8, "big")
    return n, e, d, n_bytes


def _issuer_cert(n, e, d, n_bytes, issuer_mod: bytes):
    """Construye un certificado de emisor válido firmado por la CA (para test)."""
    N = len(n_bytes)
    rec = bytearray(N)
    rec[0] = 0x6A
    rec[1] = 0x02
    rec[2:6] = from_hex("41890000")  # issuer id
    rec[6:8] = from_hex("1230")  # expiry MMYY
    rec[8:11] = from_hex("000001")  # serial
    rec[11] = 0x01  # SHA-1
    rec[12] = 0x01  # RSA
    rec[13] = len(issuer_mod)  # N_I
    rec[14] = 0x01  # exp len
    left = N - 36  # bytes de "leftmost digits"
    body = bytearray(rec[15 : 15 + left])
    body[: len(issuer_mod)] = issuer_mod
    for i in range(len(issuer_mod), left):
        body[i] = 0xBB  # relleno
    rec[15 : 15 + left] = body
    h = hashlib.sha1(bytes(rec[1 : N - 21]) + b"" + b"\x03").digest()
    rec[N - 21 : N - 1] = h
    rec[N - 1] = 0xBC
    cert = pow(int.from_bytes(bytes(rec), "big"), d, n).to_bytes(N, "big")
    return cert


def test_recover_issuer_pk_valid_and_tampered():
    n, e, d, n_bytes = _make_ca(512)
    issuer_mod = bytes(range(1, 25))  # 24 bytes de clave "emisor"
    cert = _issuer_cert(n, e, d, n_bytes, issuer_mod)

    ik = oda.recover_issuer_pk(cert, b"\x03", n_bytes, e)
    assert ik.header_ok and ik.trailer_ok and ik.format_ok
    assert ik.hash_ok and ik.valid
    assert ik.modulus == issuer_mod and ik.key_bits == 192
    assert ik.expiry == "1230"

    # certificado manipulado -> no valida
    bad = bytearray(cert)
    bad[10] ^= 0xFF
    ik2 = oda.recover_issuer_pk(bytes(bad), b"\x03", n_bytes, e)
    assert not ik2.valid


# --- assess() integración ---------------------------------------------------
def test_assess_combines_everything():
    tlvs = _tlvlist(
        [
            ("82", "7C00"),  # SDA+DDA+CVM…
            ("8E", "00000000000000001F000103"),  # CVM: noCVM + PIN claro
            ("9F07", "FF00"),  # AUC
            ("90", "AA" * 96),
            ("8F", "05"),
            ("9F32", "03"),
            ("93", "BB" * 96),
        ]
    )
    a = analyze.assess(tlvs)
    assert "SDA" in a.oda.methods_supported
    assert a.cvm is not None and len(a.cvm.rules) == 2
    assert any("Sin CVM" in f for f in a.findings)
    assert "Capacidades" in a.summary()
    assert a.oda.ca_key_bits == 768


def test_assess_verifies_issuer_cert_when_ca_given():
    n, e, d, n_bytes = _make_ca(512)
    issuer_mod = bytes(range(1, 25))
    cert = _issuer_cert(n, e, d, n_bytes, issuer_mod)
    tlvs = _tlvlist([("82", "4000"), ("90", to_hex(cert)), ("9F32", "03")])
    a = analyze.assess(tlvs, ca_modulus=n_bytes, ca_exponent=e)
    assert a.issuer_key is not None and a.issuer_key.valid
