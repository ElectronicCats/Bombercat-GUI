"""Análisis de seguridad EMV (puro): combina capacidades (AIP/AUC/TTQ), la lista
CVM y el estado de ODA en un único informe con hallazgos.

`assess(tlvs)` recibe un `core.tlv.TLVList` (p.ej. `Application.all_tlvs()` o los
TLV reconstruidos de una captura) y devuelve un `Assessment` con `.summary()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import cvm as cvmmod
from . import emvbits
from . import oda as odamod


@dataclass
class Assessment:
    aip: list
    auc: list
    ttq: list
    cvm: object | None  # cvm.CvmList | None
    oda: object  # oda.OdaReport
    issuer_key: object | None  # oda.IssuerPublicKey | None
    findings: list = field(default_factory=list)

    def summary(self, color=None) -> str:
        if color is None:

            def color(s, *a):
                return s

        L: list[str] = []

        L.append(color("Capacidades (AIP):", "bold"))
        L.append("  " + (", ".join(emvbits.set_flags(self.aip)) or "(ninguna)"))
        if self.auc:
            L.append(color("Uso permitido (AUC):", "bold"))
            L.append(
                "  " + (", ".join(emvbits.set_flags(self.auc)) or "(sin restricciones)")
            )
        if self.ttq:
            L.append(color("Terminal contactless (TTQ):", "bold"))
            L.append("  " + (", ".join(emvbits.set_flags(self.ttq)) or "(ninguna)"))

        L.append(color("CVM (verificación de titular):", "bold"))
        if self.cvm:
            for r in self.cvm.rules:
                nxt = "  →siguiente-si-falla" if r.apply_next_if_fails else ""
                L.append(f"  · {r.code_name}  [cond: {r.condition_name}]{nxt}")
        else:
            L.append("  (sin lista CVM / tag 8E)")

        L.append(color("ODA (autenticación offline):", "bold"))
        o = self.oda
        L.append(f"  métodos: {', '.join(o.methods_supported) or '(ninguno en AIP)'}")
        L.append(f"  presentes: {', '.join(sorted(o.present)) or '(ninguno)'}")
        L.append(
            f"  SDA listo: {'sí' if o.sda_ready else 'no'}   "
            f"DDA listo: {'sí' if o.dda_ready else 'no'}"
        )
        if o.ca_key_bits:
            L.append(
                f"  clave CA ~{o.ca_key_bits} bits · emisor ~{o.issuer_key_bits or '?'} bits"
            )
        if self.issuer_key is not None:
            ik = self.issuer_key
            estado = "VÁLIDO" if ik.valid else "INVÁLIDO"
            L.append(
                color(f"  cert. emisor recuperado: {estado}", "bold")
                + f"  (hdr={ik.header_ok} fmt={ik.format_ok} hash={ik.hash_ok}, "
                f"clave {ik.key_bits} bits, exp {ik.expiry})"
            )

        if self.findings:
            L.append(color("Hallazgos:", "bold"))
            for f in self.findings:
                L.append(color(f"  ! {f}", "yellow"))
        return "\n".join(L)


def assess(
    tlvs, *, ca_modulus: bytes | None = None, ca_exponent: int = 3
) -> Assessment:
    """Evalúa capacidades + CVM + ODA. Si se aporta la clave de CA, además
    recupera y valida el certificado de clave pública del emisor."""

    def find(tag):
        t = tlvs.find(tag)
        return t.value if t else None

    aip = emvbits.decode_aip(find("82") or b"")
    auc = emvbits.decode_auc(find("9F07") or b"") if find("9F07") else []
    ttq = emvbits.decode_ttq(find("9F66") or b"") if find("9F66") else []
    cvm = cvmmod.parse_cvm_list(find("8E") or b"") if find("8E") else None
    oda = odamod.oda_report(tlvs)

    issuer_key = None
    if ca_modulus:
        try:
            issuer_key = odamod.verify_issuer_certificate(tlvs, ca_modulus, ca_exponent)
        except Exception:
            issuer_key = None

    findings: list[str] = []
    if cvm:
        findings.extend(cvm.risks())
    findings.extend(oda.notes)
    if issuer_key is not None and not issuer_key.valid:
        findings.append(
            "El certificado de clave pública del emisor NO valida "
            "con la CA indicada (hash/cabecera/formato)"
        )
    return Assessment(
        aip=aip,
        auc=auc,
        ttq=ttq,
        cvm=cvm,
        oda=oda,
        issuer_key=issuer_key,
        findings=findings,
    )
