<p align="center">
  <pre>
███████╗███╗   ███╗██╗   ██╗██╗   ██╗
██╔════╝████╗ ████║██║   ██║╚██╗ ██╔╝
█████╗  ██╔████╔██║██║   ██║ ╚████╔╝
██╔══╝  ██║╚██╔╝██║╚██╗ ██╔╝  ╚██╔╝
███████╗██║ ╚═╝ ██║ ╚████╔╝    ██║
╚══════╝╚═╝     ╚═╝  ╚═══╝     ╚═╝
        C  O  N  T  R  O  L  L  E  R
  </pre>
</p>

<p align="center">
  <strong>Desarrollado por Glitchboi</strong><br>
  Seguridad desde México para todos
</p>

<p align="center">
  <img src="https://img.shields.io/badge/estado-BETA-orange" alt="Estado" />
  <img src="https://img.shields.io/badge/license-GNU_AGPLv3-blue" alt="License" />
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB" alt="Python" />
  <img src="https://img.shields.io/badge/plataforma-Linux-333" alt="Plataforma" />
  <img src="https://img.shields.io/badge/tests-238%20passing-brightgreen" alt="Tests" />
</p>

---

> ### Software en BETA
> EMVy Controller funciona y está probado (238 tests + hardware real), pero **la API, la CLI y los
> formatos de datos pueden cambiar** entre versiones. Úsalo esperando aristas y reporta lo que encuentres.

> ### Uso responsable
> Herramienta para **pruebas de seguridad autorizadas** (pentest, laboratorio, CTF) con tarjetas
> **propias o de laboratorio**. La suite **lee y explora**; los valores de "terminal" son de
> laboratorio y **no generan transacciones válidas**. **No la uses contra tarjetas ajenas ni para
> fraude.** Ver [`SECURITY.md`](SECURITY.md).

---

## Tabla de Contenidos

- [¿Qué es EMVy Controller?](#qué-es-emvy-controller)
- [Descarga (Linux)](#descarga-linux)
- [Instalación desde fuente](#instalación-desde-fuente)
- [Uso](#uso)
- [Hardware soportado](#hardware-soportado)
- [Wiki y documentación](#wiki-y-documentación)
- [Arquitectura](#arquitectura)
- [Desarrollo](#desarrollo)
- [Contribuir](#contribuir)
- [Créditos](#créditos)
- [Licencia](#licencia)

---

## ¿Qué es EMVy Controller?

**EMVy Controller** es una suite **funcional** de **pruebas de seguridad para tarjetas bancarias**:
controla múltiples lectores (chip **EMV** vía PC/SC, **NFC/contactless**, **banda magnética** y
**BomberCat**), organiza el trabajo en **proyectos**, gestiona **variables de entorno** (perfil de
terminal EMV + variables libres) y ofrece una **TUI**, una **GUI** de escritorio y una **CLI**.

Descubre y explora todo lo accesible en una tarjeta de pago, y ayuda a **perfilar terminales/POS**:

- **Descubre** aplicaciones EMV (PSE/PPSE/AIDs), lee FCI, ejecuta el GPO (AIP/AFL), lee registros y
  contadores (`GET DATA`), y decodifica pistas de **banda magnética**.
- **Analiza** la seguridad de la tarjeta: AIP/AUC, lista de **CVM**, **ODA** (SDA/DDA/CDA, claves
  débiles, verificación RSA del certificado del emisor) y genera hallazgos.
- **Escribe** en tarjetas de laboratorio y **fuzzea** terminales con pistas mutadas (magspoof),
  registros EMV mutados y **tags NDEF** malformados.
- **BomberCat**: lector EMV contactless, passthrough APDU, magspoof, **emulación** de tag NDEF y de
  **tarjeta EMV** (para perfilar/fuzzear terminales), y flasheo de firmware.
- **PoCs**: framework con runner + plugins por proyecto y plantillas ISO 8583 (sign-on / compra /
  reverso) para flujos de switch/adquirente.
- Busca **flags** automáticamente en cada byte devuelto (útil en CTF).

---

## Descarga (Linux)

Los binarios se publican en **[Releases](https://github.com/Glitchboi-sudo/EMVy_Controller/releases)**.

```bash
# Descarga el AppImage de la última release
chmod +x EMVy_Controller-*-beta-x86_64.AppImage
./EMVy_Controller-*-beta-x86_64.AppImage
```

El **AppImage** trae la **GUI** completa + núcleo + lectores PC/SC y BomberCat (serie), sin instalar
Python. Requisitos del sistema destino (no se pueden empaquetar):

| Necesitas… | Instala en el destino |
|---|---|
| **Lectores de chip (PC/SC)** | Arch: `sudo pacman -S ccid` · Debian/Ubuntu: `sudo apt install pcscd libccid` · Fedora: `sudo dnf install pcsc-lite ccid` |
| **NFC** (`nfcpy`) / **banda** (`evdev`) | deps propias del backend (opcionales) |
| **Flashear firmware** BomberCat | `arduino-cli` (o arrastrar el `.uf2` incluido a la unidad `RPI-RP2`) |

> El socket `pcscd.socket` lo **arranca la app sola** al abrir. Si no tiene permiso:
> `sudo systemctl enable --now pcscd.socket`.

---

## Instalación desde fuente

Requiere **Python 3.10+** (probado hasta 3.14). Recomendado con [`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Glitchboi-sudo/EMVy_Controller.git
cd EMVy_Controller

uv venv .venv
uv pip install --python .venv -e '.[dev,tui]'   # + [gui] [nfc] [msr] [bombercat] según tu hardware
```

Con `pip` estándar:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,tui]'
```

**Dependencias del sistema** para compilar `pyscard` (backend de chip):

| Distro | Paquetes |
|---|---|
| Arch | `sudo pacman -S ccid swig` |
| Debian/Ubuntu | `sudo apt install pcscd libpcsclite-dev swig build-essential` |
| Fedora | `sudo dnf install pcsc-lite pcsc-lite-devel swig gcc` |

Guía detallada en la **[Wiki → Instalación](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Instalación)**.

---

## Uso

### TUI (recomendada)

```bash
./emvyctl.py tui      # o: emvy tui
```

### GUI de escritorio (Qt)

```bash
uv pip install --python .venv -e '.[gui]'
./emvyctl.py gui      # o: emvy gui
```

### CLI (scripting)

```bash
./emvyctl.py readers                 # lista lectores (todos los backends)
./emvyctl.py info                    # resumen legible + búsqueda de flags
./emvyctl.py discover                # apps EMV (PPSE/PSE/bruteforce)
./emvyctl.py dump --save cap1        # captura del proyecto activo
./emvyctl.py analyze                 # análisis de seguridad EMV (AIP/AUC/CVM/ODA)
./emvyctl.py flags --file card.json  # buscar flags offline sobre un dump

# Proyectos y variables
./emvyctl.py project new lab --desc "pentest lab"
./emvyctl.py var apply contactless-kiosk       # perfil de terminal en un paso
```

Selección de lector: `-r <índice|nombre|backend|id>`. La referencia completa está en la
**[Wiki → Guía de uso](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Guía-de-uso)**.

---

## Hardware soportado

| Backend | Dependencia | Cubre | Notas |
|---|---|---|---|
| **pcsc** | pyscard | chip de contacto + contactless PC/SC | requiere `pcscd` + driver `ccid` |
| **nfc** | nfcpy | NFC/ISO-DEP (EMV contactless, Type 4) | PN532/PN533, ACR122, RC-S380 |
| **msr** | evdev / pyserial | banda magnética (HID / serie) | parsea el swipe con `core.track` |
| **bombercat** | pyserial | EMV contactless, passthrough, magspoof, emulación | Electronic Cats RP2040 |

**Degradación elegante**: si falta una dependencia o el hardware, ese backend simplemente no aporta
dispositivos — el resto sigue funcionando. Detalle en la
**[Wiki → Hardware y lectores](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Hardware-y-lectores)**.

---

## Wiki y documentación

**La documentación completa vive en la [Wiki del proyecto](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki)**:

| Página | Contenido |
|---|---|
| [Inicio](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki) | Qué es, qué hace y cómo funciona. |
| [Instalación](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Instalación) | Por distro, extras y requisitos de hardware. |
| [Guía de uso](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Guía-de-uso) | CLI, TUI, GUI y flujo de pentest sugerido. |
| [Arquitectura](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Arquitectura) | Diseño funcional, capas y el `Transceiver`. |
| [Hardware y lectores](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Hardware-y-lectores) | PC/SC, NFC, banda y BomberCat. |
| [BomberCat](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/BomberCat) | Firmware, emulación NDEF/EMV y flasheo. |
| [Variables y perfiles](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Variables-y-perfiles) | Perfil de terminal EMV y variables libres. |
| [Análisis de seguridad](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Análisis-de-seguridad) | AIP/AUC, CVM y ODA. |
| [PoCs y Cobros](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/PoCs-y-Cobros) | Framework de PoCs y switch ISO 8583. |
| [Fuzzing](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Fuzzing) | Probar terminales/POS con datos fuera de norma. |
| [FAQ](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/FAQ) | Preguntas y problemas frecuentes. |

En el repo también hay copias en [`docs/`](docs/), la wiki de arquitectura para contribuir
([`CLAUDE.md`](CLAUDE.md)) y el [`CHANGELOG.md`](CHANGELOG.md).

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
├── project/    proyectos + variables + perfiles
├── poc/        framework de PoCs (runner + plugins del proyecto)
├── tui/        interfaz TUI (Textual)
├── gui/        interfaz GUI de escritorio (PySide6/Qt)
└── cli.py      CLI para scripting
```

La abstracción clave es `Transceiver = Callable[[APDU|bytes], Response]`: **toda** la lógica EMV
recibe una función `send`, no un objeto con estado. Más en la
**[Wiki → Arquitectura](https://github.com/Glitchboi-sudo/EMVy_Controller/wiki/Arquitectura)**.

---

## Desarrollo

```bash
.venv/bin/python -m pytest tests/ -q     # suite offline (238 tests, sin hardware)
```

`tests/fakecard.py` es una tarjeta simulada (un `Transceiver` falso) que permite probar todo el flujo
EMV sin hardware. Ver [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Contribuir

Los PRs son bienvenidos. Antes de empezar, lee [`CONTRIBUTING.md`](CONTRIBUTING.md): convenciones de
código (núcleo puro, inmutabilidad, efectos en los bordes), cómo correr los tests y qué **nunca**
subir (datos de tarjeta, capturas, datos de cliente). Reporta bugs y mejoras con las plantillas de
[issues](https://github.com/Glitchboi-sudo/EMVy_Controller/issues).

---

## Créditos

Desarrollado por **[Glitchboi](https://github.com/Glitchboi-sudo)** — *Seguridad desde México para
todos*.

- Integra el framework oficial **[bombercat-tools](https://github.com/ElectronicCats/bombercat-tools)**
  de [Electronic Cats](https://electroniccats.com/) (vendorizado en `vendor/`, con su propia licencia).
- Construido sobre `pyscard`, `nfcpy`, `Textual`, `PySide6` y el ecosistema Python.

---

## Licencia

Copyright © 2026 **glitchboi**. Distribuido bajo la **[GNU Affero General Public License v3.0 o
posterior](LICENSE)** (AGPL-3.0-or-later).

El código de terceros vendorizado en `vendor/` conserva su **propia licencia** (ver
`vendor/bombercat-tools/LICENSE`) y **no** está cubierto por la AGPL de este proyecto.
