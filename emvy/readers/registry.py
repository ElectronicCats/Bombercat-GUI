"""Registro unificado de backends de lector. Único punto que usan CLI y TUI para
descubrir dispositivos (PC/SC + NFC + MSR) y abrir conexiones, saltando los
backends no disponibles sin romper.
"""
from __future__ import annotations

from . import bombercat, msr, nfc, pcsc
from .types import Capability, DeviceInfo, OpenReader, ReaderError

# Orden de preferencia: chip de contacto primero.
_BACKENDS = {m.BACKEND: m for m in (pcsc, nfc, bombercat, msr)}


def available_backends() -> dict[str, bool]:
    """Mapa backend -> ¿dependencias disponibles?"""
    return {name: mod.available() for name, mod in _BACKENDS.items()}


def list_all_devices() -> list[DeviceInfo]:
    """Todos los dispositivos detectados en todos los backends disponibles."""
    devices: list[DeviceInfo] = []
    for mod in _BACKENDS.values():
        try:
            devices.extend(mod.list_devices())
        except Exception:
            continue
    return devices


def open_device(device: DeviceInfo, *, protocol: str = "any",
                timeout: float = 30.0, on_event=None, on_wire=None) -> OpenReader:
    """Abre `device` con el backend adecuado.

    `on_event` (opcional) recibe un `TraceEvent` por cada APDU (traza de alto
    nivel, ya parseada con su status word — la implementan todos los backends
    vía `make_transceiver`). `on_wire` (opcional) recibe un `WireEvent` por cada
    línea de transporte de bajo nivel; hoy solo el backend BomberCat lo emite
    (las líneas serie del passthrough), donde ver el handshake y el framing
    crudo ayuda a depurar lecturas inestables. Los backends que no tienen una
    capa de transporte propia por debajo del APDU (PC/SC, NFC) lo ignoran: su
    `TraceEvent` ya es literalmente el comando que mandan al chip."""
    mod = _BACKENDS.get(device.backend)
    if mod is None:
        raise ReaderError(f"Backend desconocido: {device.backend!r}")
    if device.backend == "pcsc":
        return mod.open(device, protocol=protocol, on_event=on_event)
    if device.backend == "nfc":
        return mod.open(device, timeout=timeout, on_event=on_event)
    if device.backend == "bombercat":
        return mod.open(device, on_event=on_event, on_wire=on_wire, timeout=timeout)
    return mod.open(device)


def _no_devices_help() -> str:
    lines = ["No se detectó ningún lector. Estado de backends:"]
    for name, ok in available_backends().items():
        lines.append(f"  · {name:5} : {'disponible' if ok else 'no disponible (falta dependencia)'}")
    lines.append("")
    lines.append(pcsc.PCSC_HELP)
    return "\n".join(lines)


def resolve(spec: str | None, devices: list[DeviceInfo] | None = None) -> DeviceInfo:
    """Resuelve un dispositivo por índice, nombre, backend o id (subcadena)."""
    devices = devices if devices is not None else list_all_devices()
    if not devices:
        raise ReaderError(_no_devices_help())
    if spec is None:
        return devices[0]
    if spec.isdigit():
        idx = int(spec)
        if idx >= len(devices):
            raise ReaderError(f"Índice de lector {idx} fuera de rango (hay {len(devices)}).")
        return devices[idx]
    low = spec.lower()
    for d in devices:
        if low == d.backend or low in d.name.lower() or low in d.id.lower():
            return d
    raise ReaderError(
        f"Ningún lector coincide con {spec!r}. Disponibles:\n"
        + "\n".join(f"  [{i}] {d}" for i, d in enumerate(devices))
    )
