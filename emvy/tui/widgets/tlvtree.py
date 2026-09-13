"""Construcción de un árbol Textual a partir de una TLVList (reutilizable por el
explorador de tarjeta). Funciones puras de presentación sobre `core.tlv`.
"""
from __future__ import annotations

from ...core import tlv
from ...core.hexutil import ascii_printable, to_hex


def ascii_of(raw: bytes) -> str:
    """ASCII imprimible de `raw` si es mayormente texto legible; si no, "".

    Se usa para ofrecer copiar/asignar el valor en ASCII (p.ej. nombres, labels)
    además del hex."""
    if not raw:
        return ""
    s = ascii_printable(raw)                       # no imprimible -> '.'
    printable = sum(ch != "." for ch in s)
    return s if printable >= max(1, len(s) * 0.6) else ""


def _label(t: tlv.TLV) -> str:
    """Etiqueta rica de un nodo TLV (tag, nombre y, si aplica, interpretación)."""
    head = f"[b cyan]{t.tag}[/] [dim]{t.name}[/]"
    if t.constructed and t.children:
        return head
    interp = t.interpret()
    raw = to_hex(t.value)
    if interp != raw and interp != "(vacío)":
        return f"{head} = [yellow]{raw}[/] [green]→ {interp}[/]"
    return f"{head} = [yellow]{raw or '(vacío)'}[/]"


def node_data(t: tlv.TLV) -> dict:
    """Dato estructurado que acompaña a cada nodo TLV, para copiar/asignar el
    valor a una variable desde la TUI. Para tags constructivos se usa el TLV
    completo codificado (así 'copiar' devuelve el objeto entero)."""
    is_leaf = not (t.constructed and t.children)
    raw = t.value if is_leaf else t.to_bytes()
    return {"tag": t.tag, "value": to_hex(raw), "ascii": ascii_of(raw),
            "is_hex": True, "suggest": t.tag}


def add_tlvs(node, tlvs) -> None:
    """Añade recursivamente los TLV de `tlvs` como hijos de `node` (un TreeNode)."""
    for t in tlvs:
        if t.constructed and t.children:
            child = node.add(_label(t), data=node_data(t))
            add_tlvs(child, t.children)
        else:
            node.add_leaf(_label(t), data=node_data(t))
