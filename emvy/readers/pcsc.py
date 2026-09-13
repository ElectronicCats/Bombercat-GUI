"""Backend PC/SC (pyscard): lectores de chip de contacto y contactless PC/SC
(p.ej. ACR122U). Compone un `transmit` de bajo nivel con `make_transceiver`, así
que hereda gratis el manejo de 61xx/6Cxx.
"""
from __future__ import annotations

from ..core.apdu import make_transceiver
from .types import Capability, DeviceInfo, OpenReader, ReaderError

BACKEND = "pcsc"

_CONTACTLESS_HINTS = ("contactless", "picc", "nfc", "acr122", "pn53", "rfid")

PCSC_HELP = (
    "Backend PC/SC no disponible o sin lectores. Verifica:\n"
    "  1) driver instalado:  sudo pacman -S ccid\n"
    "  2) daemon activo:     sudo systemctl start pcscd.socket\n"
    "  3) lector conectado:  lsusb | grep -i reader\n"
    "  4) pyscard instalado: uv pip install --python .venv pyscard\n"
    "  5) ¿el lector aparece? pcsc_scan   (si lsusb lo ve pero pcsc_scan no,\n"
    "     el CCID no se enlazó: revisa 'journalctl -u pcscd' y reinícialo)"
)


def available() -> bool:
    try:
        import smartcard  # noqa: F401
        return True
    except Exception:
        return False


def _caps(name: str) -> frozenset[Capability]:
    low = name.lower()
    if any(h in low for h in _CONTACTLESS_HINTS):
        return frozenset({Capability.CONTACTLESS})
    return frozenset({Capability.CONTACT})


def list_devices(*, retries: int = 3, delay: float = 0.25) -> list[DeviceInfo]:
    """Lectores PC/SC detectados.

    `pcscd` suele estar activado por socket: la **primera** llamada tras un
    arranque en frío puede devolver la lista vacía porque el daemon aún no
    terminó de enumerar el USB. Por eso, si sale vacía, reintentamos unas pocas
    veces con una pausa corta (sólo penaliza el caso vacío). Si hay un lector,
    vuelve al instante.
    """
    if not available():
        return []
    import time

    from smartcard.System import readers as pcsc_readers
    names: list[str] = []
    for attempt in range(max(1, retries)):
        try:
            names = [str(r) for r in pcsc_readers()]
        except Exception:
            names = []
        if names:
            break
        if attempt < retries - 1:
            time.sleep(delay)
    return [DeviceInfo(BACKEND, n, n, _caps(n)) for n in names]


def _connect_order(protocol: str, cc) -> list[int]:
    """Secuencia de protocolos a intentar al conectar, sin duplicados.

    Muchos lectores CCID económicos (p.ej. Rocketek CR336-C) fallan la
    negociación automática `T0|T1` (el PPS) y sólo conectan si se fuerza un
    protocolo concreto. Probamos primero el pedido y luego degradamos
    `T1 → T0 → any`, así el lector sano conecta al primer intento y el
    quisquilloso encuentra un protocolo que funcione.
    """
    t0, t1 = cc.T0_protocol, cc.T1_protocol
    both = t0 | t1
    requested = {"t0": t0, "t1": t1, "any": both}.get(protocol.lower(), both)
    order: list[int] = []
    for p in (requested, t1, t0, both):
        if p not in order:
            order.append(p)
    return order


def open(device: DeviceInfo, protocol: str = "any", on_event=None) -> OpenReader:
    """Conecta con la tarjeta del lector `device` y devuelve un OpenReader."""
    if not available():
        raise ReaderError(PCSC_HELP)
    from smartcard.CardConnection import CardConnection
    from smartcard.Exceptions import CardConnectionException, NoCardException
    from smartcard.System import readers as pcsc_readers

    reader = next((r for r in pcsc_readers() if str(r) == device.id), None)
    if reader is None:
        raise ReaderError(f"Lector PC/SC no encontrado: {device.id!r}")

    # Degradación de protocolo + reset limpio entre intentos: cubre lectores
    # que fallan la negociación automática o el primer connect tras insertar.
    conn = reader.createConnection()
    last_err: Exception | None = None
    connected = False
    for proto in _connect_order(protocol, CardConnection):
        try:
            conn.connect(protocol=proto)
            connected = True
            break
        except NoCardException as e:
            raise ReaderError("No hay tarjeta insertada en el lector.") from e
        except CardConnectionException as e:
            last_err = e
            try:  # reset limpio antes de reintentar con otro protocolo
                conn.disconnect()
            except Exception:
                pass
            conn = reader.createConnection()
    if not connected:
        raise ReaderError(
            f"No se pudo conectar a la tarjeta del lector {device.name!r} "
            f"tras probar T0/T1: {last_err}"
        ) from last_err

    trace: list = []

    def transmit(apdu_bytes: bytes) -> tuple[bytes, int, int]:
        data, sw1, sw2 = conn.transmit(list(apdu_bytes))
        return bytes(data), sw1, sw2

    def atr() -> bytes:
        return bytes(conn.getATR())

    def close() -> None:
        try:
            conn.disconnect()
        except Exception:
            pass

    def emit(e):
        trace.append(e)
        if on_event:
            on_event(e)

    send = make_transceiver(transmit, on_event=emit)
    return OpenReader(device=device, close=close, transceive=send, atr=atr, trace=trace)
