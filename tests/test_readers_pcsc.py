"""Tests del backend PC/SC sin hardware.

Usan las clases reales de pyscard (constantes de protocolo y excepciones son
puros objetos Python, no requieren lector), pero con un lector/conexión falsos.
Cubren la reparación de lectores CCID quisquillosos como el Rocketek CR336-C:
degradación de protocolo `T0|T1 → T1 → T0` + reset limpio entre intentos.
"""

import pytest

pytest.importorskip("smartcard")

import smartcard.System as pcsc_system  # noqa: E402
from smartcard.CardConnection import CardConnection  # noqa: E402
from smartcard.Exceptions import CardConnectionException, NoCardException  # noqa: E402

from cardsec.readers import pcsc  # noqa: E402
from cardsec.readers.types import ReaderError  # noqa: E402

READER_NAME = "Rocketek CR336-C [CCID Interface] 00 00"


class FakeConnection:
    """Conexión pyscard falsa con negociación de protocolo programable.

    `ok_protocols` es el conjunto de protocolos con los que `connect` tiene
    éxito; con cualquier otro lanza `CardConnectionException` (simula el fallo
    de PPS de los lectores económicos). `no_card=True` lanza `NoCardException`.
    """

    def __init__(self, ok_protocols, *, no_card=False):
        self.ok_protocols = set(ok_protocols)
        self.no_card = no_card
        self.attempts = []  # protocolos intentados, en orden
        self.connected_with = None
        self.disconnected = 0

    def connect(self, protocol=None):
        self.attempts.append(protocol)
        if self.no_card:
            raise NoCardException("no card", hresult=0)
        if protocol not in self.ok_protocols:
            raise CardConnectionException(f"PPS falló para protocolo {protocol}")
        self.connected_with = protocol

    def transmit(self, apdu_list):
        # Devuelve un 9000 con el propio comando como datos (eco simple).
        return list(apdu_list), 0x90, 0x00

    def getATR(self):
        return [0x3B, 0x00]

    def disconnect(self):
        self.disconnected += 1


class FakeReader:
    """Lector pyscard falso: `str(reader)` es su id, produce FakeConnection."""

    def __init__(self, name, conn_factory):
        self.name = name
        self._factory = conn_factory
        self.created = 0

    def __str__(self):
        return self.name

    def createConnection(self):
        self.created += 1
        return self._factory()


def _install_reader(monkeypatch, conn_factory, name=READER_NAME):
    reader = FakeReader(name, conn_factory)
    monkeypatch.setattr(pcsc_system, "readers", lambda: [reader])
    return reader


def _devinfo(name=READER_NAME):
    return pcsc.DeviceInfo(pcsc.BACKEND, name, name, pcsc._caps(name))


# --- Degradación de protocolo ----------------------------------------------
def test_connect_order_dedup_and_priority():
    order = pcsc._connect_order("any", CardConnection)
    both = CardConnection.T0_protocol | CardConnection.T1_protocol
    assert order[0] == both  # el pedido va primero
    assert len(order) == len(set(order))  # sin duplicados
    assert set(order) == {CardConnection.T0_protocol, CardConnection.T1_protocol, both}


def test_connect_order_requested_first():
    order = pcsc._connect_order("t1", CardConnection)
    assert order[0] == CardConnection.T1_protocol


def test_open_falls_back_when_negotiation_fails(monkeypatch):
    """CR336-C: 'any' (T0|T1) falla el PPS pero T1 solo conecta."""
    conns = []

    def factory():
        c = FakeConnection(ok_protocols={CardConnection.T1_protocol})
        conns.append(c)
        return c

    _install_reader(monkeypatch, factory)
    with pcsc.open(_devinfo(), protocol="any") as r:
        # conectó con T1 tras degradar desde T0|T1
        assert r.transceive is not None
        assert r.atr() == b"\x3b\x00"
    # se recreó la conexión para un reset limpio antes de reintentar
    assert len(conns) == 2
    assert conns[0].disconnected == 1  # la fallida se cerró
    assert conns[1].connected_with == CardConnection.T1_protocol


def test_open_healthy_reader_connects_first_try(monkeypatch):
    both = CardConnection.T0_protocol | CardConnection.T1_protocol
    conns = []

    def factory():
        c = FakeConnection(ok_protocols={both})
        conns.append(c)
        return c

    _install_reader(monkeypatch, factory)
    with pcsc.open(_devinfo(), protocol="any") as r:
        assert r.atr() == b"\x3b\x00"
    assert len(conns) == 1  # sin reintentos
    assert conns[0].attempts == [both]


def test_open_no_card_raises_friendly(monkeypatch):
    _install_reader(monkeypatch, lambda: FakeConnection(set(), no_card=True))
    with pytest.raises(ReaderError, match="No hay tarjeta"):
        pcsc.open(_devinfo())


def test_open_all_protocols_fail(monkeypatch):
    _install_reader(monkeypatch, lambda: FakeConnection(set()))
    with pytest.raises(ReaderError, match="T0/T1"):
        pcsc.open(_devinfo())


def test_open_reader_not_found(monkeypatch):
    _install_reader(monkeypatch, lambda: FakeConnection(set()), name="Otro Lector")
    with pytest.raises(ReaderError, match="no encontrado"):
        pcsc.open(_devinfo(name=READER_NAME))


def test_list_devices_retries_on_cold_pcscd(monkeypatch):
    """pcscd frío: readers() vacío al principio y luego aparece el lector."""
    calls = {"n": 0}

    def flaky_readers():
        calls["n"] += 1
        return [] if calls["n"] < 3 else [FakeReader(READER_NAME, lambda: None)]

    monkeypatch.setattr(pcsc_system, "readers", flaky_readers)
    devs = pcsc.list_devices(retries=5, delay=0)
    assert calls["n"] == 3
    assert len(devs) == 1 and devs[0].name == READER_NAME


def test_list_devices_gives_up_empty(monkeypatch):
    monkeypatch.setattr(pcsc_system, "readers", lambda: [])
    assert pcsc.list_devices(retries=2, delay=0) == []


def test_transceive_roundtrip(monkeypatch):
    both = CardConnection.T0_protocol | CardConnection.T1_protocol
    _install_reader(monkeypatch, lambda: FakeConnection({both}))
    with pcsc.open(_devinfo()) as r:
        resp = r.transceive(bytes.fromhex("00A4040000"))
        assert resp.sw == 0x9000
