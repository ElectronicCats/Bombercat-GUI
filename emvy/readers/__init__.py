"""Capa de lectores: transporte hacia el chip/NFC/banda magnética.

Aísla todas las dependencias de hardware (pyscard, nfcpy, evdev, pyserial). El
resto del proyecto solo conoce `registry`, `OpenReader` y `DeviceInfo`.
"""

from __future__ import annotations

from . import registry  # noqa: F401
from .types import (  # noqa: F401
    Capability,
    DeviceInfo,
    OpenReader,
    ReaderError,
    TraceEvent,
    Transceiver,
)

__all__ = [
    "registry",
    "Capability",
    "DeviceInfo",
    "OpenReader",
    "ReaderError",
    "TraceEvent",
    "Transceiver",
]
