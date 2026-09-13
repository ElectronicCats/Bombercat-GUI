# Instalación

EMVy Controller corre en **Linux** con **Python 3.10+** (probado hasta 3.14). Hay dos caminos:
el **AppImage** (solo GUI, sin instalar Python) o la **instalación desde fuente** (TUI + GUI + CLI +
librería).

---

## Opción A — AppImage (rápido, solo GUI)

1. Descarga el AppImage de la última **[Release](https://github.com/Glitchboi-sudo/EMVy_Controller/releases)**.
2. Dale permiso de ejecución y ábrelo:

```sh
chmod +x EMVy_Controller-*-beta-x86_64.AppImage
./EMVy_Controller-*-beta-x86_64.AppImage
```

El AppImage incluye la GUI (PySide6), el núcleo y los lectores **PC/SC** y **BomberCat** (serie). No
incluye NFC ni banda magnética (usa la instalación desde fuente con esos extras si los necesitas).

### Requisitos del sistema destino

Algunas cosas **no se pueden empaquetar** y deben estar en el equipo:

| Distro | Lectores de chip (PC/SC) |
|---|---|
| Arch | `sudo pacman -S ccid` |
| Debian/Ubuntu | `sudo apt install pcscd libccid` |
| Fedora | `sudo dnf install pcsc-lite ccid` |

El socket `pcscd.socket` lo arranca la app sola al abrir. Si no tiene permiso (polkit), actívalo una
vez a mano: `sudo systemctl enable --now pcscd.socket`.

Para **flashear firmware** del BomberCat necesitas `arduino-cli` en el destino, o puedes arrastrar el
`.uf2` incluido a la unidad `RPI-RP2` (modo BOOTSEL) sin toolchain.

---

## Opción B — Desde fuente (TUI + GUI + CLI + librería)

### 1. Dependencias del sistema

Necesarias para compilar `pyscard` (backend de chip):

| Distro | Paquetes |
|---|---|
| Arch | `sudo pacman -S ccid swig` |
| Debian/Ubuntu | `sudo apt install pcscd libpcsclite-dev swig build-essential` |
| Fedora | `sudo dnf install pcsc-lite pcsc-lite-devel swig gcc` |

### 2. Clonar e instalar

Con [`uv`](https://docs.astral.sh/uv/) (recomendado):

```sh
git clone https://github.com/Glitchboi-sudo/EMVy_Controller.git
cd EMVy_Controller

uv venv .venv
uv pip install --python .venv -e '.[dev,tui]'
```

Con `pip` estándar:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,tui]'
```

### 3. Verificar

```sh
.venv/bin/python -m pytest tests/ -q     # 238 tests, sin hardware
./emvyctl.py readers                       # lista lectores conectados
```

---

## Extras opcionales

Instala solo lo que tu hardware necesite (se combinan: `.[tui,gui,nfc]`):

| Extra | Instala | Para |
|---|---|---|
| `tui` | textual | Interfaz TUI (recomendada) |
| `gui` | PySide6 | Interfaz GUI de escritorio (Qt) |
| `nfc` | nfcpy | Lectores NFC/contactless (PN532/PN533, ACR122, RC-S380) |
| `msr` | pyserial + evdev | Lectores de banda magnética (HID/serie) |
| `bombercat` | pyserial | BomberCat (Electronic Cats) |
| `relay` | paho-mqtt | Relay NFC (coordinador MQTT) |
| `dev` | pytest | Ejecutar la suite de pruebas |

```sh
uv pip install --python .venv -e '.[dev,tui,gui,nfc,msr,bombercat]'
```

---

## Notas por entorno

- **Wayland (KDE/GNOME/Arch)**: la GUI neutraliza automáticamente los plugins de tema del sistema que
  pueden reventar el Qt embebido de PySide6. Si el compositor sigue dando problemas, fuerza XWayland:
  `QT_QPA_PLATFORM=xcb ./emvyctl.py gui`.
- **BomberCat / arduino-cli en Linux**: subir firmware por USB puede requerir una regla udev.
  Ver [`HARDWARE.md`](HARDWARE.md) y `CLAUDE.md §12`.
