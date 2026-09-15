"""Tests del backend BomberCat con un serial falso (sin hardware)."""

import pytest

import fakeserial


@pytest.fixture
def fake_serial():
    fakeserial.install()
    yield
    fakeserial.uninstall()


def test_list_devices(fake_serial):
    from emvy.readers import bombercat

    devs = bombercat.list_devices()
    assert devs and devs[0].backend == "bombercat"
    assert "contactless" in devs[0].caps_str


def test_read_emv_json(fake_serial):
    from emvy.readers import bombercat
    from emvy.session import from_bombercat

    d = bombercat.read_emv(bombercat.list_devices()[0], amount_cents=500)
    assert d["aid"] == "A0000000031010" and d["arqc"]
    dump = from_bombercat(d)
    app = dump.applications[0]
    assert app["aid"] == "A0000000031010"
    assert app["get_data"]["9F26"] == "D6F5B2E0E50B0F9C"


def test_passthrough_transceive(fake_serial):
    from emvy.core import emv
    from emvy.readers import registry

    dev = [d for d in registry.list_all_devices() if d.backend == "bombercat"][0]
    with registry.open_device(dev) as r:
        apps = emv.discover(r.transceive, brute=False)
        assert apps and apps[0].aid == "A0000000041010"
        app = emv.select_application(r.transceive, apps[0].aid)
        resp, app = emv.get_processing_options(r.transceive, app)
        assert resp.ok and app.aip is not None
        assert len(r.trace) >= 3  # se registran los intercambios


def test_ndef_emulate_reports_reader_activity(fake_serial):
    """La emulación observable reporta CADA APDU del lector (SELECT app/CC/NDEF,
    READ off/len y la respuesta), no solo START/DONE — es la visibilidad nueva."""
    from emvy.readers import bombercat

    dev = bombercat.list_devices()[0]
    lines = bombercat.ndef_emulate(dev, "D101125504656D7679", timeout=0.5)
    assert any(l.startswith("EMU:START") for l in lines)
    assert any(l.startswith("EMU:RX SELECT-APP") for l in lines)
    assert any(l.startswith("EMU:RX READ off=") for l in lines)  # qué "sector" lee
    assert any(l.startswith("EMU:TX") for l in lines)
    assert any(l.startswith("EMU:MSG-SENT") for l in lines)
    assert any(l.startswith("EMU:DONE") for l in lines)  # se cerró (timeout→STOP)


def test_ndef_emulate_stop_callback(fake_serial):
    """`stop()` corta la emulación en cualquier momento (manda STOP → EMU:DONE)."""
    from emvy.readers import bombercat

    dev = bombercat.list_devices()[0]
    seen = {"msg": False}

    def on_line(line: str) -> None:
        if line.startswith("EMU:MSG-SENT"):
            seen["msg"] = True

    # sin timeout del host: solo se detiene cuando stop() lo pide
    lines = bombercat.ndef_emulate(
        dev,
        "D101125504656D7679",
        timeout=None,
        on_line=on_line,
        stop=lambda: seen["msg"],
    )
    assert seen["msg"]
    assert any(l.startswith("EMU:DONE") and "stop" in l for l in lines)


def test_emv_emulate_profiles_terminal(fake_serial):
    """`emv_emulate` (EMUEMV) hace que el terminal avance y revela su config:
    PPSE → SELECT AID (con esquema) → GPO con el PDOL decodificado → GEN AC."""
    from emvy.readers import bombercat

    dev = bombercat.list_devices()[0]
    seen = {"gpo": False}

    def on_line(line: str) -> None:
        if line.startswith("EMU:RX GPO"):
            seen["gpo"] = True

    lines = bombercat.emv_emulate(
        dev, timeout=None, on_line=on_line, stop=lambda: seen["gpo"]
    )
    assert any(l.startswith("EMU:START mode=emv") for l in lines)
    assert any(l.startswith("EMU:RX SELECT-PPSE") for l in lines)
    assert any("SELECT-AID" in l and "VISA" in l for l in lines)
    assert any(l.startswith("EMU:RX GPO") for l in lines)
    assert any(
        l.lstrip().startswith("PDOL TTQ(9F66)") for l in lines
    )  # dato del terminal
    assert any(l.startswith("EMU:DONE") and "stop" in l for l in lines)


def test_emv_emulate_injects_capture_data(fake_serial):
    """Con una captura, `emv_emulate` codifica AID/PAN/expiry/track2 y el firmware
    presenta ESE AID (no el Visa de prueba)."""
    from emvy.payments import EmvCard
    from emvy.readers import bombercat

    card = EmvCard(
        pan="5555444433332222",
        track2="5555444433332222D27122010000000000000F",
        expiry="2712",
        aid="A0000000041010",
        label="MC",
    )
    params = bombercat._emv_card_params(card)
    assert params.startswith("A0000000041010|5555444433332222|271231|")

    seen = {"aid": False}

    def on_line(line: str) -> None:
        if "SELECT-AID A0000000041010" in line:
            seen["aid"] = True

    lines = bombercat.emv_emulate(
        bombercat.list_devices()[0],
        card=card,
        timeout=None,
        on_line=on_line,
        stop=lambda: seen["aid"],
    )
    assert seen["aid"]  # el terminal ve el AID de la captura
    assert any(
        l.startswith("EMU:CARD") for l in lines
    )  # el firmware confirmó la inyección


def test_card_scan_to_ram_and_emulate_from_ram(fake_serial):
    """Flujo on-device: CARDSCAN guarda la tarjeta en RAM del firmware y
    emv_emulate(from_ram=True) la reemula (EMUEMV:RAM) mostrando ese AID."""
    from emvy.readers import bombercat

    dev = bombercat.list_devices()[0]
    info = bombercat.card_scan_to_ram(dev)
    assert info.get("pan") == "4111111111111111" and info.get("aid") == "A0000000031010"

    seen = {"aid": False}

    def on_line(line: str) -> None:
        if "SELECT-AID A0000000031010" in line:
            seen["aid"] = True

    lines = bombercat.emv_emulate(
        dev, from_ram=True, timeout=None, on_line=on_line, stop=lambda: seen["aid"]
    )
    assert seen["aid"]
    assert any(l.startswith("EMU:START mode=emv") for l in lines)


def test_cli_bombercat_cardscan(fake_serial, capsys):
    from emvy.cli import main

    rc = main(["bombercat", "cardscan"])
    assert rc == 0
    assert "4111111111111111" in capsys.readouterr().out


def test_resolve_port_recovers_after_renumeration(fake_serial):
    """Un DeviceInfo con un puerto POSIX que ya no existe (típico tras reflashear
    el BomberCat: el USB CDC se re-enumera) se recupera al puerto presente."""
    from emvy.readers import bombercat
    from emvy.readers.types import Capability, DeviceInfo

    stale = DeviceInfo(
        "bombercat",
        "serial:/dev/does-not-exist-xyz",
        "BomberCat (viejo)",
        frozenset({Capability.CONTACTLESS}),
    )
    assert bombercat._resolve_port(stale) == "/dev/ttyACM0"  # el fake presente


def test_reboot(fake_serial):
    """`reboot()` manda REBOOT y el firmware confirma la línea."""
    from emvy.readers import bombercat

    dev = bombercat.list_devices()[0]
    assert "REBOOT" in bombercat.reboot(dev)


def test_cli_bombercat_emv_emulate_registered():
    """El verbo `bombercat emv-emulate` está registrado en el parser."""
    from emvy.cli import build_parser

    args = build_parser().parse_args(["bombercat", "emv-emulate"])
    assert args.action == "emv-emulate"


def test_cli_bombercat_reboot(fake_serial, capsys):
    from emvy.cli import main

    rc = main(["bombercat", "reboot"])
    assert rc == 0
    assert "REBOOT" in capsys.readouterr().out


def test_passthrough_on_wire_reports_serial_lines(fake_serial):
    """`on_wire` debe recibir cada línea serie de bajo nivel (el handshake y el
    framing APDU:/RESP:), que es lo que se muestra en la consola en vivo."""
    from emvy.core import emv
    from emvy.readers import registry

    wire: list = []
    dev = [d for d in registry.list_all_devices() if d.backend == "bombercat"][0]
    with registry.open_device(dev, on_wire=wire.append) as r:
        # al conectar solo hay handshake PING/PONG (la tarjeta se detecta perezoso)
        tx = [w.text for w in wire if w.direction == "tx"]
        rx = [w.text for w in wire if w.direction == "rx"]
        assert "PING" in tx and "PONG" in rx
        assert not any(t.startswith("WAIT") for t in tx)  # aún no

        emv.discover(r.transceive, brute=False)
        # el primer APDU dispara WAIT/READY (activación perezosa) + el framing APDU:/RESP:
        tx = [w.text for w in wire if w.direction == "tx"]
        rx = [w.text for w in wire if w.direction == "rx"]
        assert any(t.startswith("WAIT") for t in tx) and any(
            t.startswith("READY") for t in rx
        )
        assert any(t.startswith("APDU:") for t in tx) and any(
            t.startswith("RESP:") for t in rx
        )
        assert all(w.transport == "serial" for w in wire)


# --- interacción directa desde la CLI: dump / write / analyze --------------
# EMVy usa el mismo `Transceiver` que cualquier lector, así que dump/escritura/
# análisis funcionan igual sobre el passthrough del firmware BomberCat.
def test_cli_bombercat_dump_full(fake_serial, capsys):
    from emvy.cli import main

    rc = main(["bombercat", "dump"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"aid": "A0000000041010"' in out
    assert '"9F36"' in out  # GET DATA llegó al dump


def test_cli_bombercat_write_reaches_card(fake_serial, capsys):
    from emvy.cli import main

    # el fakecard no soporta PUT DATA -> 6A82, pero prueba que el byte-path
    # (CLI -> passthrough -> tarjeta) funciona de punta a punta sin excepción.
    rc = main(["bombercat", "write", "data", "9F36", "0001"])
    out = capsys.readouterr().out
    assert "PUT DATA tag=9F36" in out and "6A82" in out
    assert rc == 1  # SW != 9000 -> código de salida distinto de 0


def test_cli_bombercat_analyze(fake_serial, capsys):
    from emvy.cli import main

    rc = main(["bombercat", "analyze"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Análisis EMV" in out and "A0000000041010" in out
