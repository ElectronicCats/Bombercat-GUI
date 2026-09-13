"""APDUs, status words (ISO 7816 / EMV) y el combinador `make_transceiver`.

Núcleo puro salvo `make_transceiver`, que compone una función `transmit` de bajo
nivel (la aporta cada backend de lector) en un `Transceiver` de alto nivel que
maneja automáticamente GET RESPONSE (61xx) y el reintento con Le exacto (6Cxx).
Esa composición vive aquí para que PC/SC y NFC la compartan sin duplicar lógica.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .hexutil import to_hex

# --- Instrucciones (INS) usadas por EMV / ISO 7816 -------------------------
INS_SELECT = 0xA4
INS_READ_RECORD = 0xB2
INS_GET_RESPONSE = 0xC0
INS_GET_DATA = 0xCA
INS_GET_PROCESSING_OPTIONS = 0xA8
INS_GET_CHALLENGE = 0x84
INS_INTERNAL_AUTHENTICATE = 0x88
INS_VERIFY = 0x20
INS_GENERATE_AC = 0xAE
INS_EXTERNAL_AUTHENTICATE = 0x82
INS_READ_BINARY = 0xB0
INS_UPDATE_BINARY = 0xD6
INS_WRITE_BINARY = 0xD0
INS_UPDATE_RECORD = 0xDC
INS_WRITE_RECORD = 0xD2
INS_APPEND_RECORD = 0xE2
INS_PUT_DATA = 0xDA

# --- Clases (CLA) ----------------------------------------------------------
CLA_ISO = 0x00
CLA_PROP = 0x80  # comandos propietarios EMV (GPO, GET DATA, GENERATE AC)


@dataclass(frozen=True)
class APDU:
    """Un command APDU. Serializa a bytes con codificación de longitud corta."""

    cla: int
    ins: int
    p1: int = 0x00
    p2: int = 0x00
    data: bytes = b""
    le: int | None = None  # None = sin Le; 0 = Le máximo (256)

    def to_bytes(self) -> bytes:
        out = bytearray([self.cla & 0xFF, self.ins & 0xFF, self.p1 & 0xFF, self.p2 & 0xFF])
        if self.data:
            if len(self.data) > 255:
                raise ValueError("APDU extendida no soportada (Lc > 255)")
            out.append(len(self.data))
            out.extend(self.data)
        if self.le is not None:
            out.append(self.le & 0xFF)
        return bytes(out)

    def __str__(self) -> str:
        return to_hex(self.to_bytes(), sep=" ")


@dataclass(frozen=True)
class Response:
    """Response APDU: data + status word (SW1 SW2)."""

    data: bytes
    sw1: int
    sw2: int

    @property
    def sw(self) -> int:
        return (self.sw1 << 8) | self.sw2

    @property
    def ok(self) -> bool:
        return self.sw == 0x9000

    @property
    def sw_hex(self) -> str:
        return f"{self.sw1:02X}{self.sw2:02X}"

    def sw_str(self) -> str:
        return status_word(self.sw1, self.sw2)

    def __str__(self) -> str:
        d = to_hex(self.data, sep=" ") if self.data else "(vacío)"
        return f"[{self.sw_hex}] {self.sw_str()} :: {d}"


@dataclass(frozen=True)
class TraceEvent:
    """Un intercambio de bajo nivel comando/respuesta (para trazas)."""

    command: str            # hex del comando enviado
    response: str           # hex de los datos recibidos
    sw1: int
    sw2: int
    t_ms: float = 0.0

    @property
    def sw(self) -> str:
        return f"{self.sw1:02X}{self.sw2:02X}"


# --- Diccionario de status words ------------------------------------------
_SW: dict[int, str] = {
    0x9000: "OK",
    0x6200: "Advertencia: sin cambios en memoria",
    0x6281: "Parte de datos corrupta",
    0x6282: "Fin de archivo/registro antes de leer Le bytes",
    0x6283: "Archivo seleccionado invalidado",
    0x6284: "FCI con formato no ISO 7816-4",
    0x6300: "Advertencia: autenticación fallida",
    0x6400: "Error de ejecución (estado no cambiado)",
    0x6500: "Error de memoria (estado cambiado)",
    0x6581: "Fallo de memoria",
    0x6700: "Longitud incorrecta (Lc/Le)",
    0x6800: "Función CLA no soportada",
    0x6881: "Canal lógico no soportado",
    0x6882: "Secure messaging no soportado",
    0x6900: "Comando no permitido",
    0x6981: "Comando incompatible con el archivo",
    0x6982: "Estado de seguridad no satisfecho (falta PIN/auth)",
    0x6983: "Método de autenticación bloqueado (PIN bloqueado)",
    0x6984: "Dato referenciado invalidado",
    0x6985: "Condiciones de uso no satisfechas",
    0x6986: "Comando no permitido (sin EF actual)",
    0x6987: "Falta dato esperado de secure messaging",
    0x6988: "Objeto de datos SM incorrecto",
    0x6A00: "Parámetros P1-P2 incorrectos",
    0x6A80: "Datos del campo de datos incorrectos",
    0x6A81: "Función no soportada",
    0x6A82: "Archivo o aplicación no encontrada",
    0x6A83: "Registro no encontrado",
    0x6A84: "Espacio insuficiente en archivo",
    0x6A86: "P1-P2 incorrectos",
    0x6A88: "Datos referenciados no encontrados",
    0x6B00: "P1-P2 incorrectos (offset fuera de EF)",
    0x6D00: "INS no soportado o inválido",
    0x6E00: "CLA no soportada",
    0x6F00: "Sin diagnóstico preciso",
}


def status_word(sw1: int, sw2: int) -> str:
    """Texto legible para un status word."""
    sw = (sw1 << 8) | sw2
    if sw in _SW:
        return _SW[sw]
    if sw1 == 0x61:
        return f"Hay {sw2} bytes disponibles (usar GET RESPONSE)"
    if sw1 == 0x6C:
        return f"Le incorrecto; longitud exacta = {sw2}"
    if sw1 == 0x63 and (sw2 & 0xF0) == 0xC0:
        return f"Verificación fallida, quedan {sw2 & 0x0F} intentos"
    if sw1 == 0x64 or sw1 == 0x65:
        return "Error de ejecución"
    return f"Status desconocido {sw:04X}"


# --- Constructores de APDUs comunes ---------------------------------------
def select(aid_or_name: bytes, by_name: bool = True) -> APDU:
    """SELECT por DF name (AID o nombre PSE)."""
    p1 = 0x04 if by_name else 0x00
    return APDU(CLA_ISO, INS_SELECT, p1, 0x00, aid_or_name, le=0x00)


def select_file_id(file_id: bytes, p2: int = 0x0C) -> APDU:
    """SELECT por identificador de fichero (P1=00), como exige NFC Forum Type 4
    Tag Operation para elegir el Capability Container (E103) y el fichero NDEF
    que este apunte. `p2=0x0C` (sin FCI/FCP/FMD) es lo que pide esa spec."""
    return APDU(CLA_ISO, INS_SELECT, 0x00, p2, file_id)


def read_record(record: int, sfi: int) -> APDU:
    """READ RECORD `record` del SFI dado (P2 = (sfi<<3)|4)."""
    p2 = ((sfi << 3) | 0x04) & 0xFF
    return APDU(CLA_ISO, INS_READ_RECORD, record, p2, le=0x00)


def get_response(length: int) -> APDU:
    return APDU(CLA_ISO, INS_GET_RESPONSE, 0x00, 0x00, le=length & 0xFF)


def get_data(tag: int) -> APDU:
    """GET DATA para un tag de 2 bytes (p.ej. 0x9F36)."""
    return APDU(CLA_PROP, INS_GET_DATA, (tag >> 8) & 0xFF, tag & 0xFF, le=0x00)


# --- Escritura (ISO 7816 / EMV) -------------------------------------------
def update_record(record: int, sfi: int, data: bytes) -> APDU:
    """UPDATE RECORD `record` del SFI (reemplaza el contenido del registro)."""
    p2 = ((sfi << 3) | 0x04) & 0xFF
    return APDU(CLA_ISO, INS_UPDATE_RECORD, record, p2, data)


def write_record(record: int, sfi: int, data: bytes) -> APDU:
    """WRITE RECORD (según la lógica de escritura del EF; algunas tarjetas)."""
    p2 = ((sfi << 3) | 0x04) & 0xFF
    return APDU(CLA_ISO, INS_WRITE_RECORD, record, p2, data)


def append_record(sfi: int, data: bytes) -> APDU:
    """APPEND RECORD: añade un registro a un EF lineal cíclico/variable."""
    p2 = ((sfi << 3) | 0x04) & 0xFF
    return APDU(CLA_ISO, INS_APPEND_RECORD, 0x00, p2, data)


def update_binary(offset: int, data: bytes, sfi: int | None = None) -> APDU:
    """UPDATE BINARY en un EF transparente. Con `sfi` usa identificador corto
    (P1 = 0x80|sfi, P2 = offset); si no, offset de 15 bits en P1P2."""
    if sfi is not None:
        p1, p2 = 0x80 | (sfi & 0x1F), offset & 0xFF
    else:
        p1, p2 = (offset >> 8) & 0x7F, offset & 0xFF
    return APDU(CLA_ISO, INS_UPDATE_BINARY, p1, p2, data)


def put_data(tag: int, data: bytes) -> APDU:
    """PUT DATA de un objeto (tag de 2 bytes), p.ej. para personalizar datos."""
    return APDU(CLA_PROP, INS_PUT_DATA, (tag >> 8) & 0xFF, tag & 0xFF, data)


def get_processing_options(pdol_data: bytes = b"") -> APDU:
    """GPO. El campo de datos se envuelve en el template 0x83."""
    payload = bytes([0x83, len(pdol_data)]) + pdol_data
    return APDU(CLA_PROP, INS_GET_PROCESSING_OPTIONS, 0x00, 0x00, payload, le=0x00)


def get_challenge(length: int = 8) -> APDU:
    return APDU(CLA_ISO, INS_GET_CHALLENGE, 0x00, 0x00, le=length)


def internal_authenticate(ddol_data: bytes) -> APDU:
    return APDU(CLA_ISO, INS_INTERNAL_AUTHENTICATE, 0x00, 0x00, ddol_data, le=0x00)


# --- Tipos de transporte ---------------------------------------------------
# Bajo nivel: envía bytes crudos y devuelve (data, sw1, sw2). Lo implementa cada
# backend de lector (PC/SC, NFC…).
LowLevelTransmit = Callable[[bytes], "tuple[bytes, int, int]"]

# Alto nivel: envía un APDU (o bytes) y devuelve un Response completo (con 61/6C
# ya resueltos). Es lo que consume toda la lógica EMV de `core.emv`.
Transceiver = Callable[["APDU | bytes"], Response]


def make_transceiver(
    transmit: LowLevelTransmit,
    on_event: Callable[[TraceEvent], None] | None = None,
) -> Transceiver:
    """Compone un `transmit` de bajo nivel en un `Transceiver` de alto nivel.

    Maneja automáticamente:
      * 6C xx : Le incorrecto -> reintenta con la longitud exacta.
      * 61 xx : hay datos -> los recupera con GET RESPONSE (encadenado).

    `on_event`, si se pasa, recibe un `TraceEvent` por cada intercambio crudo.
    """

    def _raw(apdu_bytes: bytes) -> tuple[bytes, int, int]:
        t0 = time.perf_counter()
        data, sw1, sw2 = transmit(apdu_bytes)
        dt = (time.perf_counter() - t0) * 1000
        data = bytes(data)
        if on_event is not None:
            on_event(TraceEvent(to_hex(apdu_bytes, sep=" "),
                                to_hex(data, sep=" "), sw1, sw2, dt))
        return data, sw1, sw2

    def send(apdu: APDU | bytes) -> Response:
        apdu_bytes = apdu.to_bytes() if isinstance(apdu, APDU) else bytes(apdu)
        data, sw1, sw2 = _raw(apdu_bytes)

        # 6C xx : longitud Le incorrecta, reintentar con la exacta (solo si no
        # había campo de datos; ISO permite reenviar el mismo comando con Le=sw2).
        if sw1 == 0x6C and len(apdu_bytes) >= 4:
            retry = bytearray(apdu_bytes[:4])
            retry.append(sw2)
            data, sw1, sw2 = _raw(bytes(retry))

        # 61 xx : hay datos disponibles, pedirlos con GET RESPONSE (encadenado)
        acc = bytearray(data)
        while sw1 == 0x61:
            more, sw1, sw2 = _raw(get_response(sw2).to_bytes())
            acc.extend(more)

        return Response(bytes(acc), sw1, sw2)

    return send
