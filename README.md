<div align="center">

# EMVy Controller

**Suite funcional de pruebas de seguridad para tarjetas bancarias**
Chip **EMV** (PC/SC) · **NFC/contactless** · **banda magnética** · **BomberCat**

[![Estado](https://img.shields.io/badge/estado-BETA-orange)](https://github.com/Glitchboi-sudo/EMVy_Controller/releases)
[![Licencia](https://img.shields.io/badge/licencia-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![Plataforma](https://img.shields.io/badge/plataforma-Linux-333)](#descarga-linux)
[![Tests](https://img.shields.io/badge/tests-238%20passing-brightgreen)](tests/)

</div>

---

> ## ⚠️ Software en BETA
>
> EMVy Controller está en **fase beta**. Funciona y está probado (238 tests, hardware real),
> pero **la API, la CLI y los formatos de datos pueden cambiar** entre versiones. Úsalo
> esperando aristas y reporta lo que encuentres.

> ## 🔒 Uso previsto y responsable
>
> Herramienta para **pruebas de seguridad autorizadas**: pentest, laboratorio, CTF e
> investigación con tarjetas **propias o de laboratorio**. La suite **lee y explora** la
> tarjeta; los valores de "terminal" son **de laboratorio** y **no generan transacciones
> válidas**.
>
> **No la uses contra tarjetas ajenas ni para fraude.** El uso indebido es responsabilidad
> exclusiva de quien lo realiza. Ver [`SECURITY.md`](SECURITY.md).

---

## ¿Qué hace?

Descubre y explora todo lo accesible en una tarjeta de pago, y ayuda a **perfilar terminales/POS**:

- **Descubre** aplicaciones EMV (PSE/PPSE/AIDs), lee FCI, ejecuta el GPO (AIP/AFL), lee registros
  y contadores (`GET DATA`), y decodifica pistas de **banda magnética**.
- **Analiza** la seguridad de la tarjeta: AIP/AUC, lista de **CVM**, **ODA** (SDA/DDA/CDA, claves
  débiles, verificación RSA del certificado del emisor) y genera hallazgos.
- **Organiza** el trabajo en **proyectos** con **variables** (perfil de terminal EMV + libres) y
  **perfiles** de terminal preconfigurados (kiosko sin CVM, POS atendido, ATM…).
- **Escribe** en tarjetas de laboratorio (UPDATE RECORD/BINARY, PUT DATA, APPEND) y **fuzzea**
  terminales con pistas mutadas (magspoof), registros EMV mutados y **tags NDEF** malformados.
- **BomberCat**: lector EMV contactless, passthrough APDU, magspoof, **emulación de tag NDEF** y
  **emulación de tarjeta EMV** (para perfilar/fuzzear terminales), flasheo de firmware.
- **PoCs**: framework con runner + plugins por proyecto y plantillas ISO 8583 (sign-on / compra /
  reverso) para flujos de switch/adquirente.
- Busca **flags** automáticamente en cada byte devuelto (útil en CTF).

Tres interfaces sobre el **mismo núcleo puro**: una **TUI** (Textual), una **GUI** de escritorio
(PySide6/Qt) y una **CLI** para scripting.

---

## Descarga (Linux)

<a name="descarga-linux"></a>

Los binarios se publican en **[Releases](https://github.com/Glitchboi-sudo/EMVy_Controller/releases)**.

```sh
# Descarga el AppImage de la última release (o hazlo desde la web de Releases)
chmod +x EMVy_Controller-*-beta-x86_64.AppImage
./EMVy_Controller-*-beta-x86_64.AppImage
```

El **AppImage** trae la **GUI** completa + núcleo + lectores PC/SC y BomberCat (serie), sin instalar
nada de Python. Requisitos del sistema destino (no se pueden empaquetar):

| Necesitas… | Instala en el destino |
|---|---|
| **Lectores de chip (PC/SC)** | Arch: `sudo pacman -S ccid` · Debian/Ubuntu: `sudo apt install pcscd libccid` · Fedora: `sudo dnf install pcsc-lite ccid` |
| **NFC** (`nfcpy`) / **banda** (`evdev`) | deps propias del backend (opcionales) |
| **Flashear firmware** BomberCat | `arduino-cli` (o arrastrar el `.uf2` incluido a la unidad `RPI-RP2`) |

> El socket `pcscd.socket` lo **arranca la app sola** al abrir (vía `systemctl start`, sin sudo en la
> mayoría de setups con polkit). Si no tiene permiso: `sudo systemctl enable --now pcscd.socket`.

¿Prefieres instalar desde el código? Ver **[Instalación desde fuente](#instalación-desde-fuente)**.

---

## Instalación desde fuente

Requiere **Python 3.10+** (probado hasta 3.14). Recomendado con [`uv`](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/Glitchboi-sudo/EMVy_Controller.git
cd EMVy_Controller

uv venv .venv
uv pip install --python .venv -e '.[dev,tui]'   # + [gui] [nfc] [msr] [bombercat] según tu hardware
```

Con `pip` estándar:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,tui]'
```

**Dependencias del sistema** para compilar `pyscard` (backend de chip):

| Distro | Paquetes |
|---|---|
| Arch | `sudo pacman -S ccid swig` |
| Debian/Ubuntu | `sudo apt install pcscd libpcsclite-dev swig build-essential` |
| Fedora | `sudo dnf install pcsc-lite pcsc-lite-devel swig gcc` |

Extras opcionales (`pyproject.toml`): `tui` (Textual) · `gui` (PySide6) · `nfc` (nfcpy) ·
`msr` (pyserial+evdev) · `bombercat` (pyserial) · `relay` (paho-mqtt) · `dev` (pytest).

---

## Uso rápido

### TUI (recomendada)

```sh
./emvyctl.py tui      # o: emvy tui
```

Pestañas: **Inicio · Proyectos · Variables · Lectores · Explorador · Consola (Flags/ISO 8583/Escritura)
· Cobros · PoC · Intercept · BomberCat · Fuzzing**. Atajo `?` abre la ayuda con todos los atajos.

### GUI de escritorio (Qt)

```sh
uv pip install --python .venv -e '.[gui]'
./emvyctl.py gui      # o: emvy gui
```

Frontend nativo con **paridad de funciones** con la TUI, barra lateral por secciones, editor de
tarjeta EMV, IDE de PoCs y una **consola cruda** que muestra todo el TX/RX del hardware.

### CLI (scripting)

```sh
./emvyctl.py readers                 # lista lectores (todos los backends)
./emvyctl.py info                    # resumen legible + búsqueda de flags
./emvyctl.py discover                # apps EMV (PPSE/PSE/bruteforce)
./emvyctl.py dump -o card.json       # volcado completo a JSON
./emvyctl.py dump --save cap1        # guardar como captura del proyecto activo
./emvyctl.py analyze                 # análisis de seguridad EMV (AIP/AUC/CVM/ODA)
./emvyctl.py flags --file card.json  # buscar flags offline sobre un dump
./emvyctl.py search 'flag\{[^}]+\}'  # regex propio

# Banda magnética
./emvyctl.py track '%B...^DOE/JOHN^2512...?;...=2512...?'

# Proyectos y variables
./emvyctl.py project new lab --desc "pentest lab"
./emvyctl.py var set amount 000000001500      # alias terminal (hex)
./emvyctl.py var set merchant_name "ACME"      # tag texto (an/ans)
./emvyctl.py var apply contactless-kiosk       # perfil de terminal en un paso
```

Selección de lector: `-r <índice|nombre|backend|id>`. El perfil de terminal para el GPO sale del
**proyecto activo**. Guía completa de comandos en **[`docs/USO.md`](docs/USO.md)**.

### Como librería

```python
from emvy.readers import registry
from emvy.session import capture_card, find_flags

dev = registry.list_all_devices()[0]
with registry.open_device(dev) as r:
    dump = capture_card(r.transceive, atr=r.atr(), reader=r.device.name)
    for hit in find_flags(dump):
        print(hit.match, "->", hit.source)
```

---

## Hardware soportado

| Backend | Dependencia | Cubre | Notas |
|---|---|---|---|
| **pcsc** | pyscard | chip de contacto + contactless PC/SC | requiere `pcscd` + driver `ccid` |
| **nfc** | nfcpy | NFC/ISO-DEP (EMV contactless, Type 4) | PN532/PN533, ACR122, RC-S380 |
| **msr** | evdev / pyserial | banda magnética (HID / serie) | parsea el swipe con `core.track` |
| **bombercat** | pyserial | EMV contactless, passthrough APDU, magspoof, relay, emulación | Electronic Cats RP2040 |

**Degradación elegante**: si falta una dependencia o el hardware, ese backend simplemente no aporta
dispositivos — el resto sigue funcionando.

### BomberCat (Electronic Cats)

```sh
./emvyctl.py bombercat setup                 # prepara el framework oficial (venv aislado)
./emvyctl.py bombercat read --save cap1      # lee EMV contactless → captura
./emvyctl.py bombercat fw list               # firmwares oficiales (UF2)
./emvyctl.py bombercat fw flash NFCGate      # descarga + flashea (bootloader UF2)
./emvyctl.py bombercat devices|status|tags|readers
```

Incluye un firmware unificado "navaja suiza" (`firmware/EMVyBomberCat/`: EMV + passthrough + tags +
magspoof + emulación NDEF/EMV). Detalles en **[`docs/HARDWARE.md`](docs/HARDWARE.md)** y en
**[`CLAUDE.md §9 y §12`](CLAUDE.md)**.

---

## Documentación

| Documento | Contenido |
|---|---|
| **[`docs/INSTALACION.md`](docs/INSTALACION.md)** | Instalación detallada por distro, extras, y requisitos de hardware. |
| **[`docs/USO.md`](docs/USO.md)** | Guía completa de la CLI, TUI y flujo de pentest sugerido. |
| **[`docs/HARDWARE.md`](docs/HARDWARE.md)** | Lectores soportados, PC/SC, NFC, banda magnética y BomberCat. |
| **[`packaging/README.md`](packaging/README.md)** | Cómo construir binarios (AppImage / .exe). |
| **[`CLAUDE.md`](CLAUDE.md)** | Wiki de arquitectura completa (referencia para contribuir). |
| **[`CONTRIBUTING.md`](CONTRIBUTING.md)** | Cómo contribuir, estilo de código y convenciones. |
| **[`CHANGELOG.md`](CHANGELOG.md)** | Historial de versiones. |

---

## Arquitectura

Principio rector: **programación funcional** — un **núcleo puro** sin IO ni estado global, y los
**efectos en los bordes** (lectores, disco, terminal).

```
emvy/
├── core/       núcleo PURO: apdu, tlv, tags, aids, atr, emv, track, ndef, cvm, oda, analyze…
├── readers/    lectores: pcsc · nfc · msr · bombercat (tras un `Transceiver`)
├── payments/   helpers de pago puros: EmvCard, ISO 8583, cryptogram, switch
├── session/    captura/volcado de tarjeta (CardDump)
├── project/    proyectos + variables (perfil terminal EMV + libres) + perfiles
├── poc/        framework de PoCs (runner + plugins del proyecto)
├── tui/        interfaz TUI (Textual)
├── gui/        interfaz GUI de escritorio (PySide6/Qt)
└── cli.py      CLI para scripting
```

La abstracción clave es `Transceiver = Callable[[APDU|bytes], Response]`: **toda** la lógica EMV
recibe una función `send`, no un objeto con estado — desacopla la lógica del backend y la hace
testeable con una tarjeta simulada. Wiki completa en **[`CLAUDE.md`](CLAUDE.md)**.

---

## Desarrollo

```sh
.venv/bin/python -m pytest tests/ -q     # suite offline (238 tests, sin hardware)
```

`tests/fakecard.py` es una tarjeta Mastercard **simulada** (un `Transceiver` falso) que permite
probar todo el flujo EMV sin hardware. Ver **[`CONTRIBUTING.md`](CONTRIBUTING.md)** para el flujo de
trabajo y las convenciones de código.

---

## Licencia

[MIT](LICENSE) © 2026 glitchboi. El código vendorizado en `vendor/` conserva su propia licencia.
