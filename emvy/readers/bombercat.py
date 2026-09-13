"""Backend BomberCat (Electronic Cats) por USB serie.

Cuatro modos, según el firmware flasheado en la placa:

  * **EMV reader (JSON)** — firmware `bombercat_emv_reader`: lee EMV contactless por
    NFC y emite `JSON_START`/`<json>`/`JSON_END` @115200. `read_emv()` lo captura.
  * **Passthrough APDU** — el mismo firmware con el parche de passthrough: acepta
    `APDU:<hex>` y responde `RESP:<hex>`. `open(mode="passthrough")` lo expone como
    un `OpenReader.transceive` normal, así todo `core.emv` funciona sobre BomberCat.
  * **Magspoof / banda** — firmware oficial @9600 (comandos `mode_ms`, `set_h`…):
    `magspoof_emit()` emula un swipe de banda magnética.
  * **Relay NFC** — comandos de host/client @9600 (el relay completo usa el
    coordinador MQTT); `relay_command()` es un envoltorio fino.

Degradación elegante: si falta `pyserial` o no hay dispositivo, `available()` es
False / `list_devices()` devuelve [] y `open()` lanza ReaderError con ayuda.
"""
from __future__ import annotations

import json
import os
import time

from ..core.apdu import make_transceiver
from ..core.hexutil import from_hex, to_hex
from .types import Capability, DeviceInfo, OpenReader, ReaderError, WireEvent

BACKEND = "bombercat"

BAUD_EMV = 115200   # firmware EMV reader / passthrough
BAUD_MAG = 9600     # firmware oficial magspoof / relay

# RP2040 (Raspberry Pi) es el MCU del BomberCat.
_RP2040_VID = 0x2E8A
_HINTS = ("bombercat", "electronic cats", "rp2040", "pico")

BOMBERCAT_HELP = (
    "Backend BomberCat no disponible. Para usarlo:\n"
    "  1) instala pyserial:  uv pip install --python .venv pyserial\n"
    "  2) conecta el BomberCat por USB (aparece como /dev/ttyACM*)\n"
    "  3) firmware EMV/passthrough @115200, o magspoof/relay @9600\n"
    "  4) permisos: pertenece al grupo 'uucp'/'dialout' o usa udev"
)


# ---------------------------------------------------------------------------
# disponibilidad / descubrimiento
# ---------------------------------------------------------------------------
def available() -> bool:
    try:
        import serial  # noqa: F401
        return True
    except Exception:
        return False


def list_devices() -> list[DeviceInfo]:
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    out = []
    for p in list_ports.comports():
        blob = " ".join(str(x) for x in (p.description, p.manufacturer, p.product)).lower()
        is_bc = (p.vid == _RP2040_VID) or any(h in blob for h in _HINTS)
        if is_bc:
            name = p.product or p.description or p.device
            out.append(DeviceInfo(BACKEND, f"serial:{p.device}", f"BomberCat ({name})",
                                  frozenset({Capability.CONTACTLESS, Capability.MAGSTRIPE})))
    return out


def _port_of(device: DeviceInfo | str) -> str:
    ident = device if isinstance(device, str) else device.id
    return ident.split(":", 1)[1] if ident.startswith("serial:") else ident


def _resolve_port(device: DeviceInfo | str) -> str:
    """Puerto serie del `device`, con recuperación si el puerto cacheado ya no
    existe. El USB CDC del BomberCat se **re-enumera** en cada reflasheo/reboot
    (p.ej. /dev/ttyACM1 → /dev/ttyACM0), así que un DeviceInfo de un escaneo
    previo apunta a un puerto muerto. Si el puerto POSIX no existe y hay UN solo
    BomberCat presente ahora, usamos ése; si no, devolvemos el original y que
    `_open_serial` falle con su mensaje de ayuda."""
    port = _port_of(device)
    if not port.startswith("/") or os.path.exists(port):
        return port                      # no-POSIX (COMx) o existe: tal cual
    present = list_devices()
    if len(present) == 1:
        return _port_of(present[0])
    for d in present:                    # varios: el primero que exista de verdad
        p = _port_of(d)
        if os.path.exists(p):
            return p
    return port


# ---------------------------------------------------------------------------
# serie (helpers)
# ---------------------------------------------------------------------------
def _open_serial(port: str, baud: int):
    if not available():
        raise ReaderError(BOMBERCAT_HELP)
    import serial
    try:
        ser = serial.Serial(port, baud, timeout=1, dsrdtr=False, rtscts=False)
    except Exception as e:
        raise ReaderError(f"No se pudo abrir {port} @ {baud}: {e}\n\n{BOMBERCAT_HELP}") from e
    # DTR debe quedar asertado: el firmware (USB CDC nativo, mbed core RP2040)
    # gatea la entrega de bytes al `Serial` de Arduino según el estado de DTR.
    # Con dtr=False el BomberCat real nunca responde a PING (confirmado en
    # hardware); no forzar False aquí.
    try:
        ser.dtr = True
    except Exception:
        pass
    time.sleep(0.3)
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    return ser


def _open_serial_retry(port: str, baud: int, tries: int = 8, delay: float = 0.25):
    """Como `_open_serial` pero reintenta si el puerto está momentáneamente
    ocupado (p.ej. otra operación acaba de soltarlo). Reeleva el último error."""
    last: Exception | None = None
    for _ in range(max(1, tries)):
        try:
            return _open_serial(port, baud)
        except ReaderError as e:
            last = e
            time.sleep(delay)
    assert last is not None
    raise last


def _wire(on_wire, direction: str, text: str) -> None:
    """Reporta una línea serie a `on_wire` (best-effort; nunca rompe la I/O)."""
    if on_wire is None or not text:
        return
    try:
        on_wire(WireEvent(direction, text, "serial"))
    except Exception:
        pass


def _readline(ser, deadline: float) -> str | None:
    while time.monotonic() < deadline:
        raw = ser.readline()
        if raw:
            return raw.decode("utf-8", errors="replace").strip()
    return None


def _writeline(ser, text: str) -> None:
    ser.write((text + "\r\n").encode())
    ser.flush()


# ---------------------------------------------------------------------------
# modo EMV reader (JSON)
# ---------------------------------------------------------------------------
def read_emv(device, amount_cents: int = 500, timeout: float = 40.0,
             on_debug=None) -> dict:
    """Pide una lectura EMV al firmware BomberCat y devuelve el dict JSON.

    Envía `SCAN <centavos>` y acumula entre `JSON_START` y `JSON_END`. Las líneas
    de depuración (`# ...`) se pasan a `on_debug` si se aporta.
    """
    ser = _open_serial(_resolve_port(device), BAUD_EMV)
    deadline = time.monotonic() + timeout
    try:
        _writeline(ser, f"SCAN {amount_cents}")
        buf: list[str] = []
        in_json = False
        while time.monotonic() < deadline:
            line = _readline(ser, deadline)
            if line is None:
                break
            if line == "JSON_START":
                in_json, buf = True, []
                continue
            if line == "JSON_END":
                try:
                    return json.loads("\n".join(buf))
                except json.JSONDecodeError as e:
                    raise ReaderError(f"JSON del BomberCat inválido: {e}")
            if in_json:
                buf.append(line)
            elif on_debug and line.startswith("#"):
                on_debug(line)
        raise ReaderError("Timeout esperando la lectura EMV del BomberCat "
                          "(¿tarjeta acercada? ¿firmware EMV reader?).")
    finally:
        ser.close()


def monitor(device, on_line, stop=None) -> None:
    """Reenvía cada línea del BomberCat a `on_line(line)` hasta que `stop()` sea
    verdadero (o Ctrl-C). Equivale a `bombercat_monitor.py`."""
    ser = _open_serial(_resolve_port(device), BAUD_EMV)
    try:
        while not (stop and stop()):
            raw = ser.readline()
            if raw:
                on_line(raw.decode("utf-8", errors="replace").rstrip())
    finally:
        ser.close()


# ---------------------------------------------------------------------------
# modo passthrough APDU  -> OpenReader.transceive
# ---------------------------------------------------------------------------
def open(device: DeviceInfo, mode: str = "passthrough", on_event=None,
         on_wire=None, timeout: float = 30.0) -> OpenReader:
    """Abre el BomberCat en modo passthrough y lo expone como lector `transceive`.

    Requiere el firmware con el parche de passthrough (comandos `PING`, `WAIT`,
    `APDU:<hex>`, `RELEASE`). Espera a que haya una tarjeta ISO-DEP presente.

    `on_wire` (opcional) recibe un `WireEvent` por cada línea serie enviada o
    recibida — el handshake (PING/WAIT/READY), el framing APDU:/RESP: y las
    líneas de depuración `#` del firmware — para verlo todo en vivo en la
    consola. Es la capa de transporte, por debajo del `TraceEvent` de APDU.
    """
    if mode != "passthrough":
        raise ReaderError(f"Modo BomberCat no soportado por open(): {mode!r} "
                          "(usa read_emv/magspoof_emit para otros modos).")
    ser = _open_serial(_resolve_port(device), BAUD_EMV)

    # Envoltorios de I/O serie que además reportan cada línea a `on_wire`. Todo
    # el tráfico serie de este lector pasa por aquí, así la consola ve
    # literalmente qué se manda y qué responde el firmware.
    def wl(text: str) -> None:
        _writeline(ser, text)
        _wire(on_wire, "tx", text)

    def rl(deadline: float) -> str | None:
        line = _readline(ser, deadline)
        if line is not None:
            _wire(on_wire, "rx", line)
        return line

    # Handshake: solo confirma el firmware. **No** espera tarjeta aquí — conectar
    # el lector debe ser instantáneo (como un lector de contacto), sin exigir una
    # tarjeta puesta. La detección de tarjeta (WAIT) se hace **perezosa**, en el
    # primer APDU (p.ej. al capturar): así "Conectar" no falla con ERR:NOCARD.
    wl("PING")
    if rl(time.monotonic() + 3) is None:
        ser.close()
        raise ReaderError("El BomberCat no respondió a PING (¿firmware passthrough?).")

    trace: list = []
    state = {"activated": False, "ats": b""}

    def _activate() -> bool:
        """WAIT hasta `timeout`: activa la tarjeta ISO-DEP si hay una. Guarda el
        ATS. Devuelve False si no aparece ninguna (sin lanzar)."""
        wl(f"WAIT {int(timeout * 1000)}")
        dl = time.monotonic() + timeout + 2
        while time.monotonic() < dl:
            line = rl(dl)
            if line is None:
                continue
            if line.startswith("READY"):
                state["activated"] = True
                if ":" in line:
                    try:
                        state["ats"] = from_hex(line.split(":", 1)[1])
                    except ValueError:
                        pass
                return True
            if line.startswith("ERR"):
                return False
        return False

    def transmit(apdu_bytes: bytes) -> tuple[bytes, int, int]:
        if not state["activated"] and not _activate():
            raise ReaderError("BomberCat: no hay tarjeta contactless. Acerca una "
                              "tarjeta NFC/EMV a la antena y reintenta.")
        wl("APDU:" + to_hex(apdu_bytes))
        dl2 = time.monotonic() + 8
        while time.monotonic() < dl2:
            line = rl(dl2)
            if line is None:
                break
            if line.startswith("RESP:"):
                data = from_hex(line[5:])
                if len(data) < 2:
                    return data, 0x6F, 0x00
                return data[:-2], data[-2], data[-1]
            if line.startswith("ERR"):
                state["activated"] = False   # tarjeta retirada: re-detectar la próxima
                raise ReaderError(f"BomberCat APDU: {line}")
            # ignora líneas de depuración '#'
        raise ReaderError("Timeout esperando RESP del BomberCat.")

    def emit(e):
        trace.append(e)
        if on_event:
            on_event(e)

    def close() -> None:
        try:
            wl("RELEASE")
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass

    send = make_transceiver(transmit, on_event=emit)
    return OpenReader(device=device, close=close, transceive=send,
                      atr=(lambda: state["ats"]), trace=trace)


# ---------------------------------------------------------------------------
# modo magspoof / banda magnética (firmware oficial @9600)
# ---------------------------------------------------------------------------
def send_command(device, cmd: str, baud: int = BAUD_MAG, timeout: float = 3.0) -> str:
    """Envía un comando de línea al firmware oficial y devuelve la respuesta."""
    ser = _open_serial(_resolve_port(device), baud)
    try:
        _writeline(ser, cmd)
        return _readline(ser, time.monotonic() + timeout) or ""
    finally:
        ser.close()


def magspoof_emit(device, track1: str | None = None, track2: str | None = None,
                  baud: int = BAUD_MAG) -> str:
    """Emula un swipe de banda magnética con el firmware magspoof.

    Selecciona modo banda (`mode_ms`) y envía las pistas. El firmware oficial
    espera la(s) pista(s); mandamos Track1 y/o Track2 con centinelas estándar.
    """
    ser = _open_serial(_resolve_port(device), baud)
    try:
        _writeline(ser, "mode_ms")
        _readline(ser, time.monotonic() + 2)
        payload = ""
        if track1:
            payload += track1 if track1.startswith("%") else f"%{track1}?"
        if track2:
            payload += track2 if track2.startswith(";") else f";{track2}?"
        _writeline(ser, payload)
        return _readline(ser, time.monotonic() + 3) or "OK"
    finally:
        ser.close()


# ---------------------------------------------------------------------------
# emulación (firmware EMVyBomberCat @115200): tag NDEF (EMU:) o tarjeta EMV (EMUEMV)
# ---------------------------------------------------------------------------
def _run_emulation(device, start_line: str, timeout: float | None,
                   on_line, stop) -> list[str]:
    """Motor común de las emulaciones observables/cancelables. Manda `start_line`
    (`EMU:<hex>` para NDEF, `EMUEMV` para tarjeta EMV) y transmite las líneas de
    estado del firmware hasta `EMU:DONE`/`ERR`, `stop()` o `timeout` (manda
    `STOP`). `timeout=None` = sin límite del host (el firmware auto-para)."""
    ser = _open_serial(_resolve_port(device), BAUD_EMV)
    lines: list[str] = []

    def _consume(line: str) -> None:
        lines.append(line)
        if on_line:
            on_line(line)

    try:
        _writeline(ser, "PING")
        if _readline(ser, time.monotonic() + 3) is None:
            raise ReaderError("El BomberCat no respondió a PING "
                              "(¿firmware EMVyBomberCat?).")
        _writeline(ser, start_line)
        deadline = None if timeout is None else time.monotonic() + timeout
        requested_stop = False
        while True:
            if stop is not None and stop():
                requested_stop = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                requested_stop = True
                break
            # deadline corto por iteración: así reaccionamos a stop()/timeout
            # sin bloquear en la lectura mientras el lector no manda nada.
            line = _readline(ser, time.monotonic() + 0.2)
            if line is None:
                continue
            _consume(line)
            if line.startswith("EMU:DONE") or line.startswith("ERR"):
                return lines
        if requested_stop:
            _writeline(ser, "STOP")
            end = time.monotonic() + 2          # consumir el EMU:DONE de confirmación
            while time.monotonic() < end:
                line = _readline(ser, end)
                if line is None:
                    break
                _consume(line)
                if line.startswith("EMU:DONE"):
                    break
        return lines
    finally:
        try:
            _writeline(ser, "STOP")
        except Exception:
            pass
        ser.close()


def ndef_emulate(device, ndef_hex: str, timeout: float | None = 200.0,
                 on_line=None, stop=None) -> list[str]:
    """Emula un tag NFC Forum Type 4 sirviendo `ndef_hex` como mensaje NDEF.

    Equivalente NFC de `magspoof_emit`, pero **observable** y **cancelable**:
    el firmware reporta cada APDU que manda el lector (`EMU:RX SELECT-APP/
    SELECT-CC/SELECT-NDEF/READ off=..len=../WRITE..`, la respuesta `EMU:TX ..`
    y `EMU:MSG-SENT n=..` al entregar un mensaje completo), lo que deja ver qué
    está leyendo el lector. Corre hasta `stop()`, `timeout` o `EMU:DONE`/`ERR`.
    Requiere el firmware **EMVyBomberCat** (comando `EMU:`)."""
    return _run_emulation(device, "EMU:" + ndef_hex, timeout, on_line, stop)


def _emv_card_params(card) -> str:
    """Codifica los datos de una tarjeta (`EmvCard`) al formato que espera el
    firmware: `<aid>|<pan>|<exp>|<track2>` (todo hex; campos vacíos permitidos).
      * aid  = AID tal cual (hex).
      * pan  = valor del tag 5A: BCD de los dígitos, padding 'F' si impar.
      * exp  = valor del tag 5F24 (YYMMDD): del `expiry` (YYMM→+"31") a 3 bytes.
      * t2   = valor del tag 57 (Track2 equivalent), ya en hex en la captura."""
    aid = (getattr(card, "aid", "") or "").replace(" ", "")
    pan = (card.pan_digits or "")
    pan_hex = pan + ("F" if len(pan) % 2 else "")
    exp = (getattr(card, "expiry", "") or "").strip()
    if len(exp) == 4:
        exp += "31"                      # YYMM → YYMMDD (día 31 por convención)
    exp_hex = exp[:6]
    t2 = (getattr(card, "track2", "") or "").replace(" ", "")
    return f"{aid}|{pan_hex}|{exp_hex}|{t2}"


def card_scan_to_ram(device, timeout: float = 25.0, on_line=None) -> dict:
    """Lee una tarjeta EMV por NFC en el BomberCat y la guarda en la **RAM del
    firmware** (comando `CARDSCAN`), para reemularla luego con
    `emv_emulate(from_ram=True)`. Flujo on-device: acerca la tarjeta al leer,
    después acerca la placa al terminal. Devuelve un dict con lo escaneado
    (`aid/pan/exp/t2len`) o lanza ReaderError si no hubo tarjeta / falló.
    Requiere el firmware **EMVyBomberCat** (comando `CARDSCAN`)."""
    ser = _open_serial(_resolve_port(device), BAUD_EMV)
    try:
        _writeline(ser, "PING")
        if _readline(ser, time.monotonic() + 3) is None:
            raise ReaderError("El BomberCat no respondió a PING (¿firmware EMVyBomberCat?).")
        _writeline(ser, "CARDSCAN")
        dl = time.monotonic() + timeout
        while time.monotonic() < dl:
            line = _readline(ser, dl)
            if line is None:
                continue
            if on_line:
                on_line(line)
            if line.startswith("EMU:SCANNED"):
                out = {"raw": line}
                for tok in line[len("EMU:SCANNED"):].split():
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        out[k] = v
                return out
            if line.startswith("ERR"):
                raise ReaderError(f"CARDSCAN: {line} (¿tarjeta contactless acercada?)")
        raise ReaderError("CARDSCAN: timeout esperando la lectura de la tarjeta.")
    finally:
        ser.close()


def emv_emulate(device, card=None, from_ram: bool = False,
                timeout: float | None = None, on_line=None, stop=None) -> list[str]:
    """Emula una **tarjeta EMV** para perfilar/fuzzear un TERMINAL de pago.

    En vez de un tag NDEF, el firmware responde al flujo EMV contactless
    (PPSE→FCI→SELECT AID→GPO→READ RECORD→GENERATE AC), para que el terminal
    AVANCE y revele su configuración: reporta `EMU:RX SELECT-PPSE`,
    `EMU:RX SELECT-AID <hex> (ESQUEMA)`, `EMU:RX GPO` con el PDOL **decodificado**
    (`  PDOL TTQ(9F66)=..`, monto, país, divisa, UN…), `READ-RECORD` y
    `GENERATE-AC` con el CDOL1 decodificado. **No** genera un criptograma válido
    (sin la clave del emisor): el objetivo es extraer el perfil del terminal, no
    aprobar un pago.

    Fuente de la tarjeta emulada:
      * `from_ram=True`  → la tarjeta guardada en la RAM del firmware por
        `card_scan_to_ram()` (comando `EMUEMV:RAM`), flujo on-device.
      * `card=<EmvCard>` → sus datos reales, inyectados desde el host
        (`EMUEMV:<aid>|<pan>|<exp>|<track2>`).
      * ninguno         → una Visa de prueba canned (`EMUEMV`).
    Cancelable con `stop()`/`timeout`. Requiere el firmware **EMVyBomberCat**."""
    if from_ram:
        start = "EMUEMV:RAM"
    elif card is not None and _emv_card_params(card).strip("|"):
        start = "EMUEMV:" + _emv_card_params(card)
    else:
        start = "EMUEMV"
    return _run_emulation(device, start, timeout, on_line, stop)


def reboot(device) -> str:
    """Reinicia el MCU del BomberCat (comando serie `REBOOT`).

    Para salir de un estado atascado (p.ej. una emulación colgada) sin apagar la
    placa a mano. El USB CDC se re-enumera tras el reset, así que **hay que
    reconectar** el lector después. Reintenta abrir el puerto si está ocupado
    (una emulación puede acabar de soltarlo)."""
    ser = _open_serial_retry(_resolve_port(device), BAUD_EMV, tries=8, delay=0.25)
    try:
        _writeline(ser, "REBOOT")
        return _readline(ser, time.monotonic() + 2) or "REBOOT"
    finally:
        try:
            ser.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# modo relay NFC (firmware oficial @9600)
# ---------------------------------------------------------------------------
def relay_command(device, cmd: str, baud: int = BAUD_MAG) -> str:
    """Envoltorio fino del protocolo de línea de relay (host/client).

    El relay NFC completo requiere el coordinador MQTT (`BomberCat/scripts/
    cordinator.py`) y dos unidades host/client; aquí solo enviamos comandos de
    control (p.ej. `mode_relay`, `set_h<NN>`, `get_config`)."""
    return send_command(device, cmd, baud=baud)
