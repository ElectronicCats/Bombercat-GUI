"""Backend NFC (nfcpy / lectores tipo PN532, ACR122 en modo libnfc, RC-S380…).

EMV contactless habla APDUs sobre ISO-DEP (Type 4 tag), así que una vez detectada
la tarjeta el `transceive` es idéntico al de PC/SC y toda la lógica de `core.emv`
funciona sin cambios.

Degradación elegante: si `nfcpy` no está instalado o no hay lector, `available()`
es False y `list_devices()` devuelve []; `open()` lanza ReaderError con ayuda.
"""

from __future__ import annotations

from ..core.apdu import make_transceiver
from .types import Capability, DeviceInfo, OpenReader, ReaderError

BACKEND = "nfc"

NFC_HELP = (
    "Backend NFC no disponible. Para usarlo:\n"
    "  1) instala nfcpy:     uv pip install --python .venv nfcpy\n"
    "  2) conecta un lector: PN532/PN533, ACR122U (libnfc) o Sony RC-S380\n"
    "  3) permisos USB:      regla udev o ejecutar con permisos sobre el dispositivo"
)

# Ruta de dispositivo por defecto que prueba nfcpy (bus USB).
_DEFAULT_PATH = "usb"


def available() -> bool:
    try:
        import nfc  # noqa: F401

        return True
    except Exception:
        return False


def _open_frontend(path: str = _DEFAULT_PATH):
    import nfc  # import perezoso

    return nfc.ContactlessFrontend(path)


def list_devices() -> list[DeviceInfo]:
    """Intenta abrir el frontend USB para reportar el lector NFC presente.

    nfcpy no enumera sin abrir; probamos a abrir y cerramos de inmediato. Si no
    hay lector o dependencia, devolvemos []."""
    if not available():
        return []
    clf = None
    try:
        clf = _open_frontend()
        name = getattr(clf, "device", None)
        name = str(name) if name else "NFC frontend (usb)"
        return [
            DeviceInfo(
                BACKEND, _DEFAULT_PATH, name, frozenset({Capability.CONTACTLESS})
            )
        ]
    except Exception:
        return []
    finally:
        if clf is not None:
            try:
                clf.close()
            except Exception:
                pass


def open(device: DeviceInfo, timeout: float = 30.0, on_event=None) -> OpenReader:
    """Abre el lector y espera una tarjeta ISO-DEP; expone `transceive`."""
    if not available():
        raise ReaderError(NFC_HELP)
    try:
        clf = _open_frontend(device.id or _DEFAULT_PATH)
    except Exception as e:
        raise ReaderError(f"No se pudo abrir el lector NFC: {e}\n\n{NFC_HELP}") from e

    # Espera un tag y lo retiene (on-connect -> False devuelve el objeto tag).
    try:
        tag = clf.connect(rdwr={"on-connect": lambda tag: False})
    except Exception as e:
        clf.close()
        raise ReaderError(f"Fallo esperando la tarjeta NFC: {e}") from e
    if tag is None or not hasattr(tag, "transceive"):
        clf.close()
        raise ReaderError("No se detectó una tarjeta ISO-DEP (Type 4 / EMV).")

    trace: list = []

    def transmit(apdu_bytes: bytes) -> tuple[bytes, int, int]:
        resp = bytes(tag.transceive(bytes(apdu_bytes)))
        if len(resp) < 2:
            return resp, 0x6F, 0x00
        return resp[:-2], resp[-2], resp[-1]

    def atr() -> bytes:
        # No hay ATR en NFC; devolvemos los bytes de identificación disponibles.
        for attr in ("ats", "historical_bytes", "identifier"):
            val = getattr(tag, attr, None)
            if val:
                return bytes(val)
        return b""

    def close() -> None:
        try:
            clf.close()
        except Exception:
            pass

    def emit(e):
        trace.append(e)
        if on_event:
            on_event(e)

    send = make_transceiver(transmit, on_event=emit)
    return OpenReader(device=device, close=close, transceive=send, atr=atr, trace=trace)
