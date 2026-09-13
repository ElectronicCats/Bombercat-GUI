"""Backend de banda magnética (Magnetic Stripe Reader).

Dos modos, ambos opcionales y con degradación elegante:
  * HID/teclado (evdev): el lector emula un teclado y "teclea" el swipe; leemos
    los eventos de tecla y reconstruimos la cadena `%B...?;...?`.
  * Serie (pyserial): lectores MSR con salida serie; leemos una línea.

La cadena cruda se entrega tal cual; `core.track.parse_swipe` la interpreta.
"""
from __future__ import annotations

import time

from .types import Capability, DeviceInfo, OpenReader, ReaderError

BACKEND = "msr"

MSR_HELP = (
    "Backend de banda magnética no disponible. Para usarlo:\n"
    "  * HID/teclado:  uv pip install --python .venv evdev   (y permisos sobre /dev/input/*)\n"
    "  * Serie:        uv pip install --python .venv pyserial (lector con salida serie)\n"
    "Especifica el dispositivo por id, p.ej. 'evdev:/dev/input/event5' o 'serial:/dev/ttyUSB0'."
)

_MSR_HINTS = ("msr", "magnetic", "magtek", "card reader", "swipe", "mag-stripe",
              "magstripe", "id tech", "idtech")


# --- disponibilidad --------------------------------------------------------
def _have_evdev() -> bool:
    try:
        import evdev  # noqa: F401
        return True
    except Exception:
        return False


def _have_serial() -> bool:
    try:
        import serial  # noqa: F401
        return True
    except Exception:
        return False


def available() -> bool:
    return _have_evdev() or _have_serial()


# --- enumeración -----------------------------------------------------------
def _evdev_devices() -> list[DeviceInfo]:
    try:
        from evdev import InputDevice, list_devices
    except Exception:
        return []
    out = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            name = dev.name or path
        except Exception:
            continue
        if any(h in name.lower() for h in _MSR_HINTS):
            out.append(DeviceInfo(BACKEND, f"evdev:{path}", f"{name} (HID)",
                                  frozenset({Capability.MAGSTRIPE})))
    return out


def _serial_devices() -> list[DeviceInfo]:
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    out = []
    for p in list_ports.comports():
        name = (p.description or p.device)
        if any(h in name.lower() for h in _MSR_HINTS):
            out.append(DeviceInfo(BACKEND, f"serial:{p.device}", f"{name} (serie)",
                                  frozenset({Capability.MAGSTRIPE})))
    return out


def list_devices() -> list[DeviceInfo]:
    return _evdev_devices() + _serial_devices()


# --- mapa de teclas HID (US) para reconstruir el swipe ---------------------
_BASE = {
    "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4", "KEY_5": "5",
    "KEY_6": "6", "KEY_7": "7", "KEY_8": "8", "KEY_9": "9", "KEY_0": "0",
    "KEY_MINUS": "-", "KEY_EQUAL": "=", "KEY_SEMICOLON": ";", "KEY_SLASH": "/",
    "KEY_SPACE": " ", "KEY_DOT": ".", "KEY_COMMA": ",", "KEY_APOSTROPHE": "'",
}
_SHIFT = {
    "KEY_5": "%", "KEY_6": "^", "KEY_SLASH": "?", "KEY_2": "@",
    "KEY_EQUAL": "+", "KEY_SEMICOLON": ":", "KEY_1": "!",
}


def _key_char(keyname: str, shift: bool) -> str:
    if keyname.startswith("KEY_") and len(keyname) == 5 and keyname[4].isalpha():
        c = keyname[4]
        return c.upper() if shift else c.lower()
    if shift and keyname in _SHIFT:
        return _SHIFT[keyname]
    return _BASE.get(keyname, "")


# --- apertura --------------------------------------------------------------
def _open_evdev(path: str) -> OpenReader:
    from evdev import InputDevice, categorize, ecodes

    dev = InputDevice(path)
    device = DeviceInfo(BACKEND, f"evdev:{path}", f"{dev.name} (HID)",
                        frozenset({Capability.MAGSTRIPE}))

    def read_swipe(timeout: float = 30.0) -> str:
        buf: list[str] = []
        shift = False
        deadline = time.monotonic() + timeout
        try:
            dev.grab()  # evita que el swipe llegue a la terminal
        except Exception:
            pass
        try:
            while time.monotonic() < deadline:
                r = dev.read_one()
                if r is None:
                    time.sleep(0.005)
                    continue
                if r.type != ecodes.EV_KEY:
                    continue
                ev = categorize(r)
                keyname = ev.keycode if isinstance(ev.keycode, str) else str(ev.keycode)
                if keyname in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"):
                    shift = ev.keystate != 0  # 1 down, 0 up
                    continue
                if ev.keystate != 1:  # solo key-down
                    continue
                if keyname == "KEY_ENTER":
                    break
                buf.append(_key_char(keyname, shift))
        finally:
            try:
                dev.ungrab()
            except Exception:
                pass
        return "".join(buf)

    return OpenReader(device=device, close=lambda: dev.close(), read_swipe=read_swipe)


def _open_serial(port: str, baud: int = 9600) -> OpenReader:
    import serial

    ser = serial.Serial(port, baudrate=baud, timeout=1)
    device = DeviceInfo(BACKEND, f"serial:{port}", f"{port} (serie)",
                        frozenset({Capability.MAGSTRIPE}))

    def read_swipe(timeout: float = 30.0) -> str:
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = ser.read(64)
            if chunk:
                buf.extend(chunk)
                if b"\r" in chunk or b"\n" in chunk:
                    break
        return buf.decode("latin-1").strip()

    return OpenReader(device=device, close=lambda: ser.close(), read_swipe=read_swipe)


def open(device: DeviceInfo) -> OpenReader:
    """Abre un lector MSR. El `device.id` indica el modo: 'evdev:<path>' o
    'serial:<port>'."""
    ident = device.id or ""
    if ident.startswith("evdev:"):
        if not _have_evdev():
            raise ReaderError(MSR_HELP)
        return _open_evdev(ident.split(":", 1)[1])
    if ident.startswith("serial:"):
        if not _have_serial():
            raise ReaderError(MSR_HELP)
        return _open_serial(ident.split(":", 1)[1])
    raise ReaderError(f"Id de dispositivo MSR no reconocido: {ident!r}\n\n{MSR_HELP}")
