"""Perfiles de terminal preconfigurados: plantillas de variables **terminal**
para escenarios comunes de pentest, aplicables en un solo paso en vez de
configurar cada variable a mano.

Cada perfil fija un puñado de alias bien entendidos: tipo de terminal (`9F35`,
EMV Book 4 Anexo A9), tipo de transacción (`9C`) y, para los contactless, el
TTQ (`9F66`, bits documentados en `core.emvbits`). Deliberadamente **no** toca
monto/moneda/país/comercio ni ninguna variable libre — eso sigue siendo
específico del engagement. Aplicar un perfil es puro: recibe la lista de
variables del proyecto y devuelve una lista nueva.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import env
from .model import Variable


@dataclass(frozen=True)
class Profile:
    id: str
    title: str
    description: str
    values: dict[str, str]  # alias -> valor, mismo formato que `var set`


PROFILES: tuple[Profile, ...] = (
    Profile(
        id="contactless-kiosk",
        title="Kiosk contactless desatendido (sin CVM)",
        description="Autoservicio (gasolinera, vending, autocobro): sin PIN pad, "
        "solo contactless, no exige verificación de titular. "
        "9F35=24 (desatendido/online-only/comercio), TTQ=20000000 "
        "(solo EMV mode, sin bits de CVM).",
        values={"terminal_type": "24", "ttq": "20000000"},
    ),
    Profile(
        id="contactless-attended",
        title="POS contactless atendido (CVM disponible)",
        description="Mostrador con terminal contactless que sí pide PIN/firma "
        "cuando el emisor lo requiere. 9F35=22 (atendido/offline con "
        "capacidad online/comercio), TTQ=36C00000 (EMV mode + "
        "contacto + PIN online + firma; CVM y criptograma online "
        "requeridos).",
        values={"terminal_type": "22", "ttq": "36C00000"},
    ),
    Profile(
        id="contact-attended",
        title="Contacto atendido genérico (PIN/firma)",
        description="Chip por contacto, mostrador atendido, compra estándar. "
        "9F35=22, tipo de transacción=00 (compra). No toca TTQ "
        "(es un tag exclusivo de contactless).",
        values={"terminal_type": "22", "txn_type": "00"},
    ),
    Profile(
        id="atm",
        title="Cajero automático (retiro, contacto, en línea)",
        description="Desatendido, institución financiera, solo en línea. "
        "9F35=14 (desatendido/online-only/institución financiera), "
        "tipo de transacción=01 (retiro de efectivo).",
        values={"terminal_type": "14", "txn_type": "01"},
    ),
)


def get(profile_id: str) -> Profile | None:
    return next((p for p in PROFILES if p.id == profile_id), None)


def list_profiles() -> tuple[Profile, ...]:
    return PROFILES


def apply_profile(variables: list[Variable], profile_id: str) -> list[Variable]:
    """Aplica un perfil sobre `variables` (por alias, kind=terminal). Puro:
    devuelve una lista nueva; no toca variables que el perfil no menciona."""
    p = get(profile_id)
    if p is None:
        raise ValueError(
            f"Perfil desconocido: {profile_id!r}. Disponibles: "
            f"{', '.join(x.id for x in PROFILES)}"
        )
    out = variables
    for alias, value in p.values.items():
        out = env.set_var(out, alias, value, kind="terminal")
    return out
