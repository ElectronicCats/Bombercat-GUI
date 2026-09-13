"""CVM List (tag 8E): decodificación de la lista de métodos de verificación de
titular y notas de riesgo (puro).

Estructura (EMV Book 3): 4 bytes Amount X + 4 bytes Amount Y + N reglas de 2
bytes. Cada regla = (byte de CV Rule, byte de condición). En el CV Rule: bit 7
(0x40) = "aplicar la siguiente regla si esta falla"; bits 6..1 (0x3F) = código de
CVM.
"""
from __future__ import annotations

from dataclasses import dataclass

from .hexutil import to_hex

# Códigos de CVM (bits 6..1 del primer byte de la regla).
CVM_CODES = {
    0x00: "Fallar procesamiento de CVM",
    0x01: "PIN en claro verificado por el ICC (offline)",
    0x02: "PIN cifrado verificado online",
    0x03: "PIN en claro por ICC + firma",
    0x04: "PIN cifrado verificado por el ICC (offline)",
    0x05: "PIN cifrado por ICC + firma",
    0x1E: "Firma (papel)",
    0x1F: "Sin CVM requerido",
}

# Condiciones (segundo byte de la regla).
CVM_CONDITIONS = {
    0x00: "Siempre",
    0x01: "Si efectivo no atendido",
    0x02: "Si no es (efectivo no atendido / manual / compra con cashback)",
    0x03: "Si el terminal soporta el CVM",
    0x04: "Si efectivo manual",
    0x05: "Si compra con cashback",
    0x06: "Si en moneda de la app y < X",
    0x07: "Si en moneda de la app y > X",
    0x08: "Si en moneda de la app y < Y",
    0x09: "Si en moneda de la app y > Y",
}


@dataclass(frozen=True)
class CvmRule:
    code: int                      # 0..0x3F
    code_name: str
    condition: int
    condition_name: str
    apply_next_if_fails: bool
    raw: str                       # 2 bytes hex


@dataclass(frozen=True)
class CvmList:
    amount_x: int
    amount_y: int
    rules: tuple[CvmRule, ...]

    def risks(self) -> list[str]:
        """Notas de riesgo relevantes para pentest."""
        notes: list[str] = []
        for r in self.rules:
            if r.code == 0x1F:
                cond = "siempre" if r.condition == 0x00 else r.condition_name.lower()
                notes.append(f"'Sin CVM requerido' presente (condición: {cond}) "
                             "→ posible ausencia de verificación de titular")
            if r.code in (0x01, 0x03):
                notes.append("PIN en claro (offline plaintext PIN) → el PIN viaja "
                             "sin cifrar hacia la tarjeta")
            if r.code == 0x1E:
                notes.append("Firma como CVM → verificación débil (no criptográfica)")
        # dedup preservando orden
        seen: set[str] = set()
        return [n for n in notes if not (n in seen or seen.add(n))]


def parse_cvm_list(data: bytes) -> CvmList | None:
    """Parsea el tag 8E. Devuelve None si es demasiado corto."""
    if len(data) < 8:
        return None
    amount_x = int.from_bytes(data[0:4], "big")
    amount_y = int.from_bytes(data[4:8], "big")
    rules: list[CvmRule] = []
    body = data[8:]
    for i in range(0, len(body) - 1, 2):
        b1, b2 = body[i], body[i + 1]
        code = b1 & 0x3F
        rules.append(CvmRule(
            code=code,
            code_name=CVM_CODES.get(code, f"desconocido (0x{code:02X})"),
            condition=b2,
            condition_name=CVM_CONDITIONS.get(b2, f"desconocida (0x{b2:02X})"),
            apply_next_if_fails=bool(b1 & 0x40),
            raw=to_hex(bytes([b1, b2])),
        ))
    return CvmList(amount_x=amount_x, amount_y=amount_y, rules=tuple(rules))
