"""Cliente TCP para enviar mensajes ISO 8583 a un host (switch/adquirente).

Efecto en el borde (socket) aislado del codec puro (`iso8583`). Enmarca el
mensaje con un prefijo de longitud de `header` bytes big-endian (2 es lo más
común; 0 = sin prefijo) y lee la respuesta con el mismo esquema.

Uso previsto: pruebas **autorizadas** contra hosts de laboratorio/propios.
"""
from __future__ import annotations

import socket


def frame(data: bytes, header: int = 2) -> bytes:
    """Añade el prefijo de longitud (header bytes) al mensaje."""
    if header == 0:
        return bytes(data)
    return len(data).to_bytes(header, "big") + bytes(data)


def _recv_n(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def send_message(host: str, port: int, data: bytes, *, header: int = 2,
                 timeout: float = 5.0) -> bytes:
    """Conecta, envía `data` enmarcado y devuelve el cuerpo de la respuesta.

    Con `header>0` lee primero esos bytes de longitud y luego el cuerpo; con
    `header==0` devuelve lo que llegue en una lectura.
    """
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(frame(data, header))
        if header == 0:
            return sock.recv(65535)
        hdr = _recv_n(sock, header)
        if len(hdr) < header:
            return b""
        n = int.from_bytes(hdr, "big")
        return _recv_n(sock, n)
