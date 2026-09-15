"""Gestión de variables de entorno del proyecto.

Dos clases de variable:
  * **terminal**: parámetro del perfil de terminal EMV, mapeado a un tag; su
    conjunto se convierte en un `TerminalProfile` (tag->bytes) que alimenta los
    DOL (PDOL/CDOL/DDOL) en `core.emv`.
  * **user**: par clave-valor libre (secrets, notas, plantillas).

Las operaciones CRUD son **puras**: reciben una lista de `Variable` y devuelven
una lista nueva (no mutan). El IO (load/save) está separado al final.

Codificación de valores de variable terminal según el formato del tag:
  * an/ans (texto)  -> el `value` es texto ASCII.
  * n/b/cn (binario)-> el `value` es hex.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.emv import default_terminal_profile
from ..core.hexutil import from_hex, to_hex
from ..core.tags import tag_fmt, tag_name
from .model import Variable

# --- alias amistosos -> tag EMV -------------------------------------------
ALIASES: dict[str, str] = {
    "amount": "9F02",
    "amount_other": "9F03",
    "country": "9F1A",
    "currency": "5F2A",
    "tvr": "95",
    "txn_date": "9A",
    "txn_type": "9C",
    "unpredictable_number": "9F37",
    "un": "9F37",
    "terminal_type": "9F35",
    "terminal_caps": "9F33",
    "addl_terminal_caps": "9F40",
    "ifd_serial": "9F1E",
    "ttq": "9F66",
    "merchant_name": "9F4E",
    "mcc": "9F15",
    "merchant_id": "9F16",
    "terminal_id": "9F1C",
    "txn_time": "9F21",
    "txn_seq": "9F41",
}
# tag -> nombre amistoso (primero que aparezca)
TAG_ALIAS: dict[str, str] = {}
for _name, _tag in ALIASES.items():
    TAG_ALIAS.setdefault(_tag, _name)


# --- resolución de tag / clasificación -------------------------------------
def resolve_tag(name: str) -> str | None:
    """Devuelve el tag EMV para `name` (alias o tag hex válido), o None."""
    low = name.lower()
    if low in ALIASES:
        return ALIASES[low]
    up = name.upper()
    # ¿parece un tag EMV? (hex de 1-2 bytes)
    try:
        raw = from_hex(up)
    except ValueError:
        return None
    if 1 <= len(raw) <= 2:
        return up
    return None


def is_text_tag(tag: str) -> bool:
    return tag_fmt(tag) in ("an", "ans")


# --- codificación de valores ----------------------------------------------
def encode_value(tag: str, value: str) -> bytes:
    """Texto->bytes para tags an/ans; hex->bytes para el resto."""
    if is_text_tag(tag):
        return value.encode("latin-1")
    return from_hex(value)


def decode_value(tag: str, raw: bytes) -> str:
    """bytes->texto para tags an/ans; bytes->hex para el resto."""
    if is_text_tag(tag):
        return raw.decode("latin-1")
    return to_hex(raw)


def make_variable(
    name: str, value: str, kind: str | None = None, description: str = ""
) -> Variable:
    """Crea una Variable, infiriendo kind/tag si no se especifica."""
    tag = resolve_tag(name)
    if kind is None:
        kind = "terminal" if tag is not None else "user"
    if kind == "terminal":
        tag = tag or resolve_tag(name)
        if tag is None:
            raise ValueError(
                f"{name!r} no es un tag EMV ni un alias conocido; "
                f"usa un tag hex (p.ej. 9F02) o un alias ({', '.join(sorted(ALIASES))})."
            )
        # valida que el valor codifique
        encode_value(tag, value)
        return Variable(
            name=name,
            value=value,
            kind="terminal",
            tag=tag,
            description=description or tag_name(tag),
        )
    return Variable(
        name=name, value=value, kind="user", tag=None, description=description
    )


# --- CRUD puro sobre list[Variable] ----------------------------------------
def get_var(variables: list[Variable], name: str) -> Variable | None:
    for v in variables:
        if v.name.lower() == name.lower():
            return v
    return None


def set_var(
    variables: list[Variable],
    name: str,
    value: str,
    kind: str | None = None,
    description: str = "",
) -> list[Variable]:
    """Añade o reemplaza la variable `name`. Devuelve una lista nueva."""
    new = make_variable(name, value, kind, description)
    out = [v for v in variables if v.name.lower() != name.lower()]
    out.append(new)
    return out


def del_var(variables: list[Variable], name: str) -> list[Variable]:
    """Elimina la variable `name`. Devuelve una lista nueva."""
    return [v for v in variables if v.name.lower() != name.lower()]


def to_terminal_profile(variables: list[Variable]) -> dict[str, bytes]:
    """Construye el TerminalProfile (tag->bytes) desde las variables terminal."""
    profile: dict[str, bytes] = {}
    for v in variables:
        if v.kind == "terminal" and v.tag:
            try:
                profile[v.tag] = encode_value(v.tag, v.value)
            except ValueError:
                continue
    return profile


def user_vars(variables: list[Variable]) -> dict[str, str]:
    """Variables libres como dict nombre->valor."""
    return {v.name: v.value for v in variables if v.kind == "user"}


# --- semilla por defecto ---------------------------------------------------
def default_variables() -> list[Variable]:
    """Perfil de terminal por defecto como lista de Variables editables.

    El Unpredictable Number (9F37) se fija a 00000000 para reproducibilidad;
    puedes cambiarlo o el flujo EMV usará el del perfil tal cual."""
    out: list[Variable] = []
    for tag, raw in default_terminal_profile().items():
        if tag == "9F37":
            raw = bytes.fromhex("00000000")
        name = TAG_ALIAS.get(tag, tag)
        out.append(
            Variable(
                name=name,
                value=decode_value(tag, raw),
                kind="terminal",
                tag=tag,
                description=tag_name(tag),
            )
        )
    return out


# --- IO (load/save) --------------------------------------------------------
def load_variables(path: Path) -> list[Variable]:
    """Carga variables desde un JSON; si no existe, devuelve los defaults."""
    if not path.exists():
        return default_variables()
    data = json.loads(path.read_text())
    return [Variable.from_dict(d) for d in data]


def save_variables(path: Path, variables: list[Variable]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([v.to_dict() for v in variables], indent=2, ensure_ascii=False)
    )
