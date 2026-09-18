"""Contratos de la capa de lectores.

Un lector abierto se representa de forma **funcional**: un `OpenReader` es un
registro inmutable de *callables* (`transceive`, `atr`, `read_swipe`, `close`) —
composición de funciones en lugar de herencia. Cada backend (PC/SC, NFC, MSR) es
un módulo que produce estos registros; nada más del proyecto sabe de pyscard,
nfcpy o evdev.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from ..core.apdu import TraceEvent, Transceiver  # noqa: F401  (re-export)


class ReaderError(RuntimeError):
    """Error de lector/transporte (sin dispositivo, driver ausente, etc.)."""


@dataclass(frozen=True)
class WireEvent:
    """Un evento de transporte de **bajo nivel**, por debajo del APDU: una línea
    de la conexión serie enviada/recibida (BomberCat: `PING`, `WAIT 30000`,
    `READY:`, `APDU:<hex>`, `RESP:<hex>`…), o una nota informativa. Complementa
    al `TraceEvent` (que es el intercambio APDU ya parseado con su status word):
    aquí se ve literalmente **qué se manda y qué responde** el hardware, útil
    para depurar (handshake, detección de tarjeta, framing).

    `direction`: `"tx"` (enviado al lector) · `"rx"` (recibido) · `"info"` (nota).
    """

    direction: str
    text: str
    transport: str = ""  # "serial", "pcsc", …


class Capability(str, Enum):
    CONTACT = "contact"  # chip EMV de contacto (ISO 7816)
    CONTACTLESS = "contactless"  # NFC / ISO 14443 (EMV contactless)
    MAGSTRIPE = "magstripe"  # banda magnética (ISO 7813)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DeviceInfo:
    """Descripción de un dispositivo detectado (dato puro, sin conexión abierta)."""

    backend: str  # "pcsc" | "nfc" | "msr"
    id: str  # identificador estable dentro del backend
    name: str  # nombre legible
    capabilities: frozenset[Capability] = frozenset()

    def has(self, cap: Capability) -> bool:
        return cap in self.capabilities

    @property
    def caps_str(self) -> str:
        return ", ".join(sorted(str(c) for c in self.capabilities)) or "?"

    def __str__(self) -> str:
        return f"[{self.backend}] {self.name} ({self.caps_str})"


@dataclass(frozen=True)
class OpenReader:
    """Un lector conectado: registro de callables. Los campos no aplicables al
    tipo de lector quedan en None (p.ej. `read_swipe` en un lector de chip, o
    `transceive`/`atr` en uno de banda magnética)."""

    device: DeviceInfo
    close: Callable[[], None]
    transceive: Transceiver | None = None
    atr: Callable[[], bytes] | None = None
    read_swipe: Callable[[float], str] | None = None
    trace: list[TraceEvent] = field(default_factory=list)

    # -- azúcar de uso como context manager --------------------------------
    def __enter__(self) -> "OpenReader":
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.close()
        except Exception:
            pass

    # -- helpers ------------------------------------------------------------
    def send(self, apdu) -> "object":
        """Envía un APDU (requiere un lector con `transceive`)."""
        if self.transceive is None:
            raise ReaderError(
                f"El lector {self.device.name!r} no soporta APDUs "
                f"(capacidades: {self.device.caps_str})."
            )
        return self.transceive(apdu)

    def swipe(self, timeout: float = 30.0) -> str:
        """Lee un swipe de banda magnética (requiere `read_swipe`)."""
        if self.read_swipe is None:
            raise ReaderError(f"El lector {self.device.name!r} no lee banda magnética.")
        return self.read_swipe(timeout)
