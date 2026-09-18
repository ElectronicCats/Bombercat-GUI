"""EMVyController — suite funcional de pruebas de seguridad para tarjetas
bancarias (chip EMV, NFC/contactless y banda magnética) vía múltiples lectores.

Arquitectura por capas:

    cardsec.core      — núcleo PURO (apdu, tlv, tags, aids, atr, emv, track, search)
    cardsec.readers   — capa de lectores (PC/SC, NFC, MSR) con `Transceiver`
    cardsec.session   — captura/volcado de tarjeta sobre `send`
    cardsec.project   — proyectos + variables de entorno (perfil terminal + libres)
    cardsec.tui       — interfaz TUI (Textual)
    cardsec.cli       — CLI para scripting

Uso rápido como librería:

    from cardsec.readers import registry
    from cardsec.core import emv

    dev = registry.list_all_devices()[0]
    with registry.open_device(dev) as rdr:
        for app in emv.discover(rdr.transceive):
            print(app.aid, app.scheme)
"""

from __future__ import annotations

__version__ = "0.5.0"
__release__ = "BETA"  # canal de publicación (se muestra junto a la versión)

from . import core  # noqa: F401  (subpaquetes con IO se importan bajo demanda)

__all__ = ["core", "__version__", "__release__"]
