"""Adaptador de `bombercat-tools` (Electronic Cats), vendorizado en
`vendor/bombercat-tools/`. EMVy lo maneja por **subprocess** contra su propio
venv aislado — así el framework conserva sus dependencias con pines propios y no
contamina el venv de EMVy.

Expone:
  * `locate()` / `ensure_venv()` — ubicación y bootstrap perezoso del venv.
  * `run_passthrough(args)` — ejecuta heredando la terminal (para `flash`,
    `device list`, `relay`, o passthrough libre): salida rica/interactiva.
  * `run_json(args)` — captura stdout y extrae el/los objeto(s) JSON (para
    `tags/readers --json`).
  * helpers: `version()`, `devices()`, `fw_list()`, `flash()`, `tags_read()`,
    `readers_read()`, `setup_env_passthrough()` / `setup_env_gui()` (v1.3.0:
    reglas udev + membresía de grupos, con elevación pkexec para la GUI).

EMVy está fijado al tag `v1.3.0` del framework (ver `PINNED_TAG`): el gitlink
del submódulo `vendor/bombercat-tools` apunta exactamente a ese tag. En v1.3.0
`tags`/`readers` están gated por capacidad de firmware y pasan por el
auto-flash; `_env()` fija `BOMBERCAT_AUTO_FLASH=never` para que EMVy nunca
dispare un flasheo/prompt implícito por subprocess (ver `_env`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import config


class BombercatToolsError(RuntimeError):
    pass


# Tag del submódulo `vendor/bombercat-tools` al que EMVy está fijado. El
# gitlink del repo padre apunta a este mismo tag (git submodule), así que el
# checkout vendorizado queda clavado aquí y no deriva. `version()` reporta el
# tag git real (no el fichero VERSION del upstream, que quedó en 1.2.0.0
# incluso en v1.3.0).
PINNED_TAG = "v1.3.0"


# ---------------------------------------------------------------------------
# Ubicación / venv
# ---------------------------------------------------------------------------
def locate() -> Path:
    """Ruta del checkout de bombercat-tools; error claro si falta."""
    root = config.bombercat_tools_dir()
    if not (root / "bombercat.py").exists():
        raise BombercatToolsError(
            f"No encuentro bombercat-tools en {root}.\n"
            "Vendorízalo (o define EMVY_BOMBERCAT_TOOLS) y corre 'emvy bombercat setup'."
        )
    return root


def _venv_python(root: Path) -> Path:
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return root / ".venv" / sub / exe


def venv_ready(root: Path | None = None) -> bool:
    root = root or locate()
    py = _venv_python(root)
    if not py.exists():
        return False
    # 'serial' es la primera dependencia que importa bombercat.py
    r = subprocess.run(
        [str(py), "-c", "import serial, click, rich"], capture_output=True
    )
    return r.returncode == 0


def ensure_venv(root: Path | None = None, *, log=None) -> Path:
    """Crea el venv del framework e instala sus deps la primera vez. Idempotente."""
    root = root or locate()
    py = _venv_python(root)
    if venv_ready(root):
        return py

    def say(m):
        (log or (lambda _: None))(m)

    req = root / "requirements.txt"
    if shutil.which("uv"):
        say("Creando venv de bombercat-tools con uv…")
        subprocess.run(["uv", "venv", str(root / ".venv")], check=True)
        subprocess.run(
            ["uv", "pip", "install", "--python", str(py), "-r", str(req)], check=True
        )
    else:
        say("Creando venv de bombercat-tools con venv+pip…")
        subprocess.run([sys.executable, "-m", "venv", str(root / ".venv")], check=True)
        subprocess.run([str(py), "-m", "pip", "install", "-q", "-U", "pip"], check=True)
        subprocess.run(
            [str(py), "-m", "pip", "install", "-q", "-r", str(req)], check=True
        )

    if not venv_ready(root):
        raise BombercatToolsError(
            "El venv de bombercat-tools quedó incompleto tras instalar deps."
        )
    return py


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------
def _base_cmd(root: Path) -> list[str]:
    return [str(ensure_venv(root)), "bombercat.py"]


def _env() -> dict:
    e = dict(os.environ)
    e.setdefault("NO_COLOR", "1")
    e.setdefault("TERM", "dumb")
    # bombercat-tools >= v1.3.0: los grupos de detección (`tags`/`readers`)
    # están *gated* por capacidad de firmware y enrutan por el orquestador de
    # auto-flash. Su política es ASK en una TTY / NEVER en un pipe; como EMVy
    # invoca por subprocess capturando stdout, un ASK dejaría un prompt de
    # confirmación INVISIBLE bloqueado en stdin. Fijamos NEVER para que, si la
    # placa no trae la capacidad, el comando falle limpio (mismatch de firmware)
    # en vez de colgarse — el usuario flashea explícitamente desde el panel.
    # Versiones antiguas de las tools ignoran esta variable (inocuo).
    e.setdefault("BOMBERCAT_AUTO_FLASH", "never")
    return e


def run_passthrough(args: list[str], *, log=None) -> int:
    """Ejecuta el framework heredando stdin/stdout/stderr (interactivo/rico)."""
    root = locate()
    ensure_venv(root, log=log)
    cmd = _base_cmd(root) + list(args)
    return subprocess.run(cmd, cwd=str(root), env=_env()).returncode


def run_capture(
    args: list[str], *, timeout: float | None = 120
) -> subprocess.CompletedProcess:
    root = locate()
    ensure_venv(root)
    cmd = _base_cmd(root) + list(args)
    return subprocess.run(
        cmd, cwd=str(root), env=_env(), capture_output=True, text=True, timeout=timeout
    )


def run_json(args: list[str], *, timeout: float | None = 120):
    """Ejecuta y extrae JSON de stdout (para comandos con `--json`)."""
    cp = run_capture(args, timeout=timeout)
    objs = _extract_json(cp.stdout)
    if not objs:
        # bombercat-tools >= v1.3.0 imprime los errores de mismatch de firmware
        # (BomberCatError) con rich, que suele ir a stdout — inclúyelo también
        # para que el mensaje real ("la placa corre X; este comando necesita Y")
        # llegue al usuario, no solo el stderr.
        tail = (cp.stderr.strip() or cp.stdout.strip())[:400]
        raise BombercatToolsError(
            f"El comando no devolvió JSON (rc={cp.returncode}).\n{tail}"
        )
    return objs if len(objs) > 1 else objs[0]


def _extract_json(text: str):
    """Recupera objetos JSON de una salida que puede traer banner/tablas rich."""
    out = []
    # intento 1: el texto entero
    try:
        return [json.loads(text)]
    except Exception:
        pass
    # intento 2: por líneas que parezcan JSON (una por línea, caso --json)
    for line in text.splitlines():
        s = line.strip()
        if s and s[0] in "{[":
            try:
                out.append(json.loads(s))
            except Exception:
                continue
    return out


# ---------------------------------------------------------------------------
# Helpers de alto nivel
# ---------------------------------------------------------------------------
def version() -> str:
    """Versión del checkout vendorizado, sin la `v` inicial (los sitios que la
    muestran ya prefijan `v`).

    Preferimos el tag git real (`git describe`) porque EMVy fija el submódulo en
    `PINNED_TAG` y el fichero VERSION del upstream quedó desactualizado (dice
    1.2.0.0 incluso en el tag v1.3.0). Si git no está disponible, caemos al
    fichero VERSION.
    """
    try:
        root = locate()
    except BombercatToolsError:
        return "?"
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        tag = r.stdout.strip()
        if r.returncode == 0 and tag:
            return tag.lstrip("v")
    except Exception:
        pass
    try:
        return (root / "VERSION").read_text().strip()
    except Exception:
        return "?"


def devices() -> int:
    return run_passthrough(["device", "list"])


def status(port: str | None = None) -> int:
    return run_passthrough(["status"] + (["-p", port] if port else []))


def fw_list() -> int:
    return run_passthrough(["flash", "--list"])


def flash(
    name: str,
    *,
    port: str | None = None,
    device_id: int | None = None,
    yes: bool = False,
    log=None,
) -> int:
    args = ["flash", name]
    if port:
        args += ["-p", port]
    if device_id is not None:
        args += ["-d", str(device_id)]
    if yes:
        args += ["-y"]
    return run_passthrough(args, log=log)


# --- variantes que CAPTURAN la salida (para la TUI; no heredan stdout) -----
def parse_fw_names(text: str) -> list[str]:
    """Extrae los nombres de firmware de la tabla rich de `flash --list`."""
    names: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("│"):  # solo filas de tabla ligera
            continue
        cells = [c.strip() for c in s.strip("│").split("│")]
        if len(cells) < 2:
            continue
        name = cells[0]
        if (
            name
            and name != "Firmware"
            and all(ch.isalnum() or ch in "._-" for ch in name)
        ):
            names.append(name)
    return names


def fw_list_names(timeout: float = 90) -> list[str]:
    """Nombres de firmware disponibles (captura y parsea `flash --list`)."""
    cp = run_capture(["flash", "--list"], timeout=timeout)
    return parse_fw_names(cp.stdout)


def flash_capture(
    name: str,
    *,
    port: str | None = None,
    device_id: int | None = None,
    timeout: float = 300,
):
    """Flashea `name` capturando la salida (para mostrarla en la TUI). Siempre
    con `-y` (no interactivo). Devuelve el CompletedProcess."""
    args = ["flash", name, "-y"]
    if port:
        args += ["-p", port]
    if device_id is not None:
        args += ["-d", str(device_id)]
    return run_capture(args, timeout=timeout)


def devices_text(timeout: float = 30) -> str:
    return run_capture(["device", "list"], timeout=timeout).stdout


def status_text(port: str | None = None, timeout: float = 30) -> str:
    return run_capture(
        ["status"] + (["-p", port] if port else []), timeout=timeout
    ).stdout


def tags_read(timeout: int = 20):
    # bombercat-tools >= v1.3.0 añade un campo `model` por fila (fingerprint del
    # chip resuelto host-side desde ATQA/SAK); es aditivo, el JSON se pasa tal cual.
    return run_json(["tags", "read", "--json", "-t", str(timeout)])


def readers_read(timeout: int = 20):
    return run_json(["readers", "read", "--json", "-t", str(timeout)])


# ---------------------------------------------------------------------------
# Estado de la placa / gating por capacidad (bombercat-tools >= v1.3.0)
# ---------------------------------------------------------------------------
# `bombercat status` NO ofrece `--json` (verificado en v1.3.0): solo imprime una
# tabla rich con name/version/detected/capabilities. La parseamos igual que
# `parse_fw_names` hace con `flash --list` (filas que empiezan por `│`).
def _table_rows(text: str) -> dict[str, str]:
    """Genérico: extrae pares clave/valor de una tabla rich de **2 columnas**
    (Campo/Valor), tolerando continuación de celda (rich parte el valor en
    varias líneas cuando no cabe en el ancho de la tabla). Reutilizado por
    `parse_status`, `parse_relay_config` y `parse_relay_status` — todas son la
    misma forma de tabla (`bombercat status`/`relay config show`/`relay status`)."""
    fields: dict[str, str] = {}
    last: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("│"):  # solo filas de la tabla ligera
            continue
        cells = [c.strip() for c in s.strip("│").split("│")]
        if len(cells) < 2:
            continue
        key, val = cells[0], cells[1]
        if key:
            fields[key] = val
            last = key
        elif last:  # continuación: rich partió el valor en varias líneas
            fields[last] = f"{fields[last]} {val}".strip()
    return fields


def parse_status(text: str) -> dict:
    """Extrae {name, version, detected, capabilities:[...]} de la tabla de
    `bombercat status`. Puro/testeable contra salida canned."""
    fields = _table_rows(text)
    caps = [
        c.strip()
        for c in fields.get("capabilities", "").split(",")
        if c.strip() and c.strip() != "—"
    ]
    return {
        "name": fields.get("name", ""),
        "version": fields.get("version", ""),
        "detected": fields.get("detected", ""),
        "capabilities": caps,
    }


def status_json(port: str | None = None, timeout: float = 30) -> dict:
    """Estado de la placa como dict plano (parsea la tabla de `status`).

    Lanza `BombercatToolsError` si nada respondió en el puerto (no hay tabla)."""
    args = ["status"] + (["-p", port] if port else [])
    cp = run_capture(args, timeout=timeout)
    st = parse_status(cp.stdout)
    if not st["name"]:
        tail = (cp.stderr.strip() or cp.stdout.strip())[:400]
        raise BombercatToolsError(
            f"No se pudo leer el estado de la placa (rc={cp.returncode}).\n{tail}"
        )
    return st


def capability_present(cap: str, *, port: str | None = None) -> bool:
    """True si la placa (según `status`) declara la capacidad `cap`."""
    try:
        return cap in status_json(port=port)["capabilities"]
    except BombercatToolsError:
        return False


# Capacidad -> imagen `.uf2` (stem) que la provee. Espejo de
# `requirements.CAPABILITY_PROVIDER` del vendor, DUPLICADO a propósito para no
# importar del otro venv; `test_capability_image_matches_vendor` asegura que no
# derive. Los stems coinciden con los nombres que espera `flash <NOMBRE>`.
CAPABILITY_IMAGE: dict[str, str] = {
    "tags": "DetectTags",
    "readers": "DetectReaders",
    "mifare": "MifareClassic",
    "magspoof": "magspoof",
    "relay": "NFCGate",
    "config": "NFCGate",
    "capture": "NFCGate",
}


def image_for_capability(cap: str) -> str:
    """Imagen `.uf2` (stem) a flashear para habilitar `cap`."""
    try:
        return CAPABILITY_IMAGE[cap]
    except KeyError:
        raise BombercatToolsError(
            f"La capacidad {cap!r} no tiene una imagen canónica asociada."
        )


def identify(port: str | None = None, timeout: float = 30):
    """Parpadea el LED de la placa (`identify`), capturando la salida."""
    return run_capture(["identify"] + (["-p", port] if port else []), timeout=timeout)


# ---------------------------------------------------------------------------
# magspoof (imagen magspoof.uf2) — emulación de banda magnética
# ---------------------------------------------------------------------------
# El CLI del vendor conversa con el REPL del firmware magspoof. `show` y
# `card list` ofrecen `--json` (verificado en v1.3.0); `play`/`card add`/
# `card select`/`nfc visa` solo confirman en texto → devolvemos el
# CompletedProcess para volcarlo con `log_result`. El `timeout` es el del
# subproceso, NO un flag del CLI (estos subcomandos no aceptan `-t`).
def _port_args(port: str | None) -> list[str]:
    return ["-p", port] if port else []


def magspoof_show(port: str | None = None, timeout: float = 20) -> dict:
    """Tarjeta activa cargada en la placa (`magspoof show --json`) →
    `{t1, t2, btn, analysis:{...}}`."""
    data = run_json(["magspoof", "show", "--json"] + _port_args(port), timeout=timeout)
    return data[0] if isinstance(data, list) else data


def magspoof_play(port: str | None = None, timeout: float = 20):
    """Reproduce un swipe de la tarjeta activa (`magspoof play`)."""
    return run_capture(["magspoof", "play"] + _port_args(port), timeout=timeout)


def magspoof_card_list(port: str | None = None, timeout: float = 20) -> list[dict]:
    """Tarjetas del store persistente (`magspoof card list --json`).

    Emite un objeto JSON por tarjeta; un store vacío es un estado válido (lista
    vacía), por eso NO usa `run_json` (que trataría "sin JSON" como error)."""
    cp = run_capture(
        ["magspoof", "card", "list", "--json"] + _port_args(port), timeout=timeout
    )
    return [o for o in _extract_json(cp.stdout) if isinstance(o, dict)]


def magspoof_card_add(
    name: str,
    *,
    t1: str | None = None,
    t2: str | None = None,
    port: str | None = None,
    timeout: float = 20,
):
    """Agrega una tarjeta al store (`magspoof card add <name> [--t1] [--t2]`)."""
    args = ["magspoof", "card", "add", name]
    if t1:
        args += ["--t1", t1]
    if t2:
        args += ["--t2", t2]
    return run_capture(args + _port_args(port), timeout=timeout)


def magspoof_card_select(name: str, *, port: str | None = None, timeout: float = 20):
    """Marca `name` como tarjeta activa (`magspoof card select <name>`)."""
    return run_capture(
        ["magspoof", "card", "select", name] + _port_args(port), timeout=timeout
    )


def magspoof_nfc_visa(port: str | None = None, timeout: float = 30):
    """Emulación Visa contactless por NFC (`magspoof nfc visa`)."""
    return run_capture(["magspoof", "nfc", "visa"] + _port_args(port), timeout=timeout)


# ---------------------------------------------------------------------------
# Mifare Classic (imagen MifareClassic.uf2) — recuperación de claves + dump
# ---------------------------------------------------------------------------
# El grupo `tags mifare` del CLI del vendor conversa con el REPL del firmware
# MifareClassic (v1.3.0). Flujo típico: `keys` (claves por defecto) → `check`
# (prueba el diccionario contra cada sector y escribe las claves recuperadas a
# un fichero `sector:keyA:keyB`) → `dump` (usa ese fichero para volcar la
# tarjeta a JSON) → `restore` (escribe el dump de vuelta). Los ficheros
# intermedios (keyfile, dump JSON) los gestiona la GUI en `<proyecto>/artifacts`.
#
# Verificado por `--help` (v1.3.0): `keys` ofrece `--json` (JSONL, un objeto por
# clave, como `magspoof card list`); `check`/`dump`/`restore` producen ficheros
# — `check` con `--output-keys FILE`, `dump` con `--keys-file`/`--out`, `restore`
# con `--dump`. `dump --json` emite el volcado en stdout. `restore` pediría
# confirmación interactiva al escribir el bloque 0; como el subproceso NO tiene
# TTY, pasamos SIEMPRE `--yes` para que no se cuelgue esperando en stdin.


def mifare_keys(port: str | None = None, timeout: float = 20) -> list[dict]:
    """Claves por defecto integradas en el firmware (`tags mifare keys --json`).

    Emite un objeto JSON por clave (JSONL) → `[{"name": .., "key": ..}, …]`;
    por eso NO usa `run_json` (JSONL, no un único documento). No requiere tarjeta."""
    cp = run_capture(
        ["tags", "mifare", "keys", "--json"] + _port_args(port), timeout=timeout
    )
    return [o for o in _extract_json(cp.stdout) if isinstance(o, dict)]


def mifare_check(
    sector_keys_out,
    *,
    sectors: int = 16,
    keys: list | None = None,
    force: bool = True,
    port: str | None = None,
    timeout: float = 120,
):
    """Recupera las claves de la tarjeta y las escribe a `sector_keys_out`
    (`tags mifare check --output-keys FILE`), el fichero `sector:keyA:keyB` que
    consume `mifare_dump`. `keys` son diccionarios extra (`--keys FILE`, repetible);
    `--force` sobrescribe el fichero si existe. Devuelve `CompletedProcess`
    (volcar con `log_result`)."""
    args = [
        "tags",
        "mifare",
        "check",
        "--output-keys",
        str(sector_keys_out),
        "--sectors",
        str(sectors),
    ]
    for k in keys or []:
        args += ["--keys", str(k)]
    if force:
        args.append("--force")
    return run_capture(args + _port_args(port), timeout=timeout)


def mifare_dump(
    keys_file,
    out_json,
    *,
    sectors: int = 16,
    force: bool = True,
    port: str | None = None,
    timeout: float = 180,
) -> dict:
    """Vuelca la tarjeta a JSON canónico usando el fichero de claves de `check`
    (`tags mifare dump --keys-file FILE --out FILE --json`). Escribe `out_json`
    y devuelve el mismo volcado como `dict` (uid + bloques por sector)."""
    args = [
        "tags",
        "mifare",
        "dump",
        "--keys-file",
        str(keys_file),
        "--out",
        str(out_json),
        "--sectors",
        str(sectors),
        "--json",
    ]
    if force:
        args.append("--force")
    data = run_json(args + _port_args(port), timeout=timeout)
    return data[0] if isinstance(data, list) else data


def mifare_restore(
    dump_json,
    *,
    sectors: int | None = None,
    write_block0: bool = False,
    skip_trailers: bool = False,
    port: str | None = None,
    timeout: float = 180,
):
    """Escribe un dump JSON de vuelta a la tarjeta (`tags mifare restore --dump
    FILE --yes`). `write_block0` reescribe el bloque 0 (UID/BCC/SAK, solo tarjetas
    "magic"); `skip_trailers` omite los trailers de sector. Siempre pasa `--yes`
    (sin TTY en el subproceso). Devuelve `CompletedProcess`."""
    args = ["tags", "mifare", "restore", "--dump", str(dump_json), "--yes"]
    if sectors is not None:
        args += ["--sectors", str(sectors)]
    if write_block0:
        args.append("--write-block0")
    if skip_trailers:
        args.append("--skip-trailers")
    return run_capture(args + _port_args(port), timeout=timeout)


# ---------------------------------------------------------------------------
# Relay NFCGate (imagen NFCGate.uf2) — config + run/stop/status + captura pcap
# ---------------------------------------------------------------------------
# El grupo `relay` del CLI del vendor configura y arranca un relay APDU sobre
# WiFi/TCP contra un `nfcgate-server`; `capture` toca el mismo tap para volcar
# los APDUs relayados a pcap. Verificado por `--help`/lectura de
# `modules/nfcgate/cli.py` y `modules/capture/cli.py` (v1.3.0): NINGÚN
# subcomando de este grupo ofrece `--json` (`config show`/`status` imprimen
# tablas rich de 2 columnas, iguales en forma a la de `status` → reusan
# `_table_rows`); `config wifi`/`config nfcgate`/`run`/`stop` solo confirman en
# texto. `monitor` y `capture start` son streaming SIN FIN (hasta Ctrl-C o que
# el firmware corte el link) — no encajan en el patrón `run_capture(timeout=…)`
# de las demás capacidades; ver `capture_run` más abajo para cómo se acota.


def parse_relay_config(text: str) -> dict:
    """`relay config show` → {fw, role, ssid, server, port, session, state}."""
    fields = _table_rows(text)
    return {
        k: fields.get(k, "")
        for k in ("fw", "role", "ssid", "server", "port", "session", "state")
    }


def relay_config_show(port: str | None = None, timeout: float = 20) -> dict:
    """Configuración actual del relay (`relay config show`)."""
    cp = run_capture(["relay", "config", "show"] + _port_args(port), timeout=timeout)
    return parse_relay_config(cp.stdout)


def relay_config_wifi(
    ssid: str,
    password: str = "",
    *,
    save: bool = True,
    port: str | None = None,
    timeout: float = 20,
):
    """Fija las credenciales WiFi (`relay config wifi --ssid --password`)."""
    args = ["relay", "config", "wifi", "--ssid", ssid, "--password", password]
    args.append("--save" if save else "--no-save")
    return run_capture(args + _port_args(port), timeout=timeout)


def relay_config_nfcgate(
    server: str,
    session: int,
    role: str,
    *,
    save: bool = True,
    port: str | None = None,
    timeout: float = 20,
):
    """Fija servidor/sesión/rol (`relay config nfcgate --server --session --role`).
    `role` es `"reader"` (lee una tarjeta física) o `"card"` (la emula a un
    terminal); `session` 1..255 debe coincidir en ambos peers."""
    args = [
        "relay",
        "config",
        "nfcgate",
        "--server",
        server,
        "--session",
        str(session),
        "--role",
        role,
    ]
    args.append("--save" if save else "--no-save")
    return run_capture(args + _port_args(port), timeout=timeout)


def parse_relay_status(text: str) -> dict:
    """`relay status` → {state, link_connected, peer_present, relayed}."""
    fields = _table_rows(text)

    def yn(v: str) -> bool:
        return v.strip().lower() == "yes"

    return {
        "state": fields.get("state", ""),
        "link_connected": yn(fields.get("link connected", "")),
        "peer_present": yn(fields.get("peer present", "")),
        "relayed": fields.get("APDU pairs relayed", "0"),
    }


def relay_status(port: str | None = None, timeout: float = 20) -> dict:
    """Estado en vivo del relay (`relay status`)."""
    cp = run_capture(["relay", "status"] + _port_args(port), timeout=timeout)
    return parse_relay_status(cp.stdout)


# `run` es bloqueante EN EL PROPIO CLI del vendor: acepta el arranque y sondea
# `status` internamente hasta 'relaying'/'error' o su propio presupuesto
# (~45 s, ver `_RUN_BRINGUP_TIMEOUT` en modules/nfcgate/cli.py). El timeout por
# defecto de `run_capture` le da margen para agotar ese presupuesto solo.
def relay_run(port: str | None = None, timeout: float = 55):
    """Arranca el relay y espera a que llegue a 'relaying' (o falle)."""
    return run_capture(["relay", "run"] + _port_args(port), timeout=timeout)


def relay_stop(port: str | None = None, timeout: float = 20):
    """Detiene el relay (`relay stop`)."""
    return run_capture(["relay", "stop"] + _port_args(port), timeout=timeout)


def capture_stop(port: str | None = None, timeout: float = 15):
    """Desarma el tap de captura (`capture stop`) — idempotente: sirve tanto
    para pararlo a mano como para limpiar un tap dejado armado por
    `capture_run` tras matar el subproceso al agotar su duración."""
    return run_capture(["capture", "stop"] + _port_args(port), timeout=timeout)


def capture_run(
    output,
    *,
    duration: float = 30,
    force: bool = True,
    strict: bool = False,
    port: str | None = None,
) -> tuple[subprocess.CompletedProcess, bool]:
    """Captura los APDUs relayados a un fichero `.pcap` durante `duration`
    segundos (`capture start -o FILE`).

    El comando del vendor no tiene noción de duración — corre hasta Ctrl-C o
    que el link caiga — así que la acotamos con el propio timeout de
    `subprocess.run`: al vencer, `TimeoutExpired` trae en `.stdout`/`.stderr`
    lo que el proceso alcanzó a escribir antes de matarlo (`subprocess.run` lo
    recolecta en su `except` antes de re-lanzar). Un `kill()` duro salta el
    `finally` de `capture start` (que desarma el tap con `capture off`), así
    que **siempre** se llama a `capture_stop` después, gane o pierda la
    carrera contra la duración — es una operación idempotente en el firmware.

    Devuelve `(CompletedProcess, timed_out)`: `timed_out=True` si se alcanzó
    la duración (la captura seguía activa); `False` si el propio comando
    terminó antes (p.ej. el link se perdió) dentro del plazo."""
    args = ["capture", "start", "-o", str(output)]
    if force:
        args.append("--force")
    if strict:
        args.append("--strict")
    args += _port_args(port)
    try:
        cp = run_capture(args, timeout=duration)
        timed_out = False
    except subprocess.TimeoutExpired as e:
        cp = subprocess.CompletedProcess(e.cmd, -1, e.stdout or "", e.stderr or "")
        timed_out = True
    finally:
        try:
            capture_stop(port=port)
        except Exception:
            pass  # best-effort: si ya se desarmó solo, no es un error
    return cp, timed_out


# ---------------------------------------------------------------------------
# setup-env (bombercat-tools >= v1.3.0): reglas udev + membresía de grupos
# ---------------------------------------------------------------------------
def setup_env_passthrough() -> int:
    """Ejecuta `bombercat setup-env` heredando la terminal (para la CLI).

    El comando necesita root y NO pide contraseña por sí mismo: se corre con
    `sudo emvy bombercat setup-env`. Si no es root, imprime el `sudo …` exacto.
    """
    return run_passthrough(["setup-env"])


def setup_env_gui(*, progress=None) -> subprocess.CompletedProcess:
    """Instala reglas udev + añade al usuario a `dialout`/`plugdev` con elevación
    gráfica (`pkexec`), capturando la salida — para el botón del panel Firmware.

    `setup-env` de las tools exige geteuid()==0, así que se eleva con pkexec.
    Como pkexec limpia el entorno (no propaga `SUDO_USER`), pasamos el usuario
    real explícito por `env SUDO_USER=…` para que los grupos se apliquen a él y
    no a root. Sin pkexec, devuelve el comando `sudo` a ejecutar a mano.
    """
    root = locate()
    py = ensure_venv(root, log=progress)
    inner = [str(py), "bombercat.py", "setup-env"]

    if os.name == "nt":
        raise BombercatToolsError(
            "setup-env es solo para Linux (reglas udev + usermod)."
        )

    if os.geteuid() == 0:  # ya root: directo
        return subprocess.run(
            inner,
            cwd=str(root),
            env=_env(),
            capture_output=True,
            text=True,
            timeout=120,
        )

    pkexec = shutil.which("pkexec")
    if not pkexec:
        sudo_cmd = "sudo " + " ".join(inner)
        raise BombercatToolsError(
            "Se requiere root y no encuentro `pkexec` para elevar gráficamente.\n"
            f"Ejecuta a mano en una terminal:\n  cd {root} && {sudo_cmd}"
        )

    user = os.environ.get("SUDO_USER") or _login_name()
    # `pkexec env SUDO_USER=<user> <py> bombercat.py setup-env`: env corre como
    # root fijando la variable que _target_user() de las tools lee.
    cmd = [pkexec, "env", f"SUDO_USER={user}", *inner]
    return subprocess.run(
        cmd, cwd=str(root), env=_env(), capture_output=True, text=True, timeout=180
    )


def _login_name() -> str:
    try:
        import getpass

        return getpass.getuser()
    except Exception:
        return os.environ.get("USER", "")
