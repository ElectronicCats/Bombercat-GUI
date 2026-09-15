#!/usr/bin/env python3
"""
Genera certificado autofirmado EC P-256 para BomberCat EMV Reader.
Salida: certs.h listo para incluir en el sketch de Arduino.

Requisito:  pip install cryptography
Uso:        python3 generate_cert.py
"""
import datetime, ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

key = ec.generate_private_key(ec.SECP256R1())

subject = issuer = x509.Name(
    [
        x509.NameAttribute(NameOID.COMMON_NAME, "bombercat.local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BomberCat"),
    ]
)

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
    .add_extension(
        x509.SubjectAlternativeName(
            [
                x509.IPAddress(ipaddress.ip_address("192.168.4.1")),
                x509.DNSName("bombercat.local"),
            ]
        ),
        critical=False,
    )
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .sign(key, hashes.SHA256())
)

cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
key_pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
).decode()


def to_c(s):
    lines = s.strip().split("\n")
    return "\n".join(f'  "{line}\\n"' for line in lines) + ";"


header = f"""// AUTO-GENERADO por generate_cert.py — NO subir a control de versiones
// Certificado autofirmado EC P-256 para 192.168.4.1 / bombercat.local
// Válido hasta: {datetime.datetime.utcnow() + datetime.timedelta(days=3650):%Y-%m-%d}
#pragma once

static const char SERVER_CERT_PEM[] =
{to_c(cert_pem)}

static const char SERVER_KEY_PEM[] =
{to_c(key_pem)}
"""

with open("certs.h", "w") as f:
    f.write(header)

print("✓ certs.h generado.")
print(
    f"  Cert válido hasta: {datetime.datetime.utcnow() + datetime.timedelta(days=3650):%Y-%m-%d}"
)
print()
print("En Chrome/Firefox, al entrar a https://192.168.4.1:")
print("  'Avanzado' → 'Continuar a 192.168.4.1 (no seguro)'")
