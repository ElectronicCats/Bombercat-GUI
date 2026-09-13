# Hardware soportado

EMVy Controller aísla el hardware detrás de la abstracción `Transceiver`, así que la misma lógica EMV
funciona por cualquier backend. Si falta una dependencia o el hardware, ese backend simplemente no
aporta dispositivos (**degradación elegante**).

| Backend | Dependencia | Cubre | Notas |
|---|---|---|---|
| **pcsc** | `pyscard` | chip de contacto + contactless PC/SC | requiere `pcscd` + driver `ccid` |
| **nfc** | `nfcpy` | NFC/ISO-DEP (EMV contactless, Type 4) | PN532/PN533, ACR122 (libnfc), RC-S380 |
| **msr** | `evdev` / `pyserial` | banda magnética (HID / serie) | parsea el swipe con `core.track` |
| **bombercat** | `pyserial` | EMV contactless, passthrough APDU, magspoof, relay, emulación | Electronic Cats RP2040 |

---

## PC/SC (lectores de chip)

Es el backend por defecto y el más estable. Requiere el daemon `pcscd` y el driver CCID del sistema
(ver [`INSTALACION.md`](INSTALACION.md)).

```sh
lsusb | grep -i reader        # verifica el lector (p.ej. Alcor AU9540)
emvy readers                   # lo debe listar como backend 'pcsc'
emvy atr                       # inserta una tarjeta y lee su ATR
```

El socket `pcscd.socket` lo arranca/para la app automáticamente (`systemctl` vía polkit, sin sudo en
la mayoría de setups); si no tiene permiso, actívalo a mano: `sudo systemctl enable --now pcscd.socket`.

---

## NFC / contactless

Con `nfcpy` (extra `[nfc]`). EMV contactless habla APDUs sobre ISO-DEP, así que el mismo `core.emv`
funciona sin cambios. También lee tags **NFC Forum Type 4** (NDEF) con `emvy dump --mode nfc`.

---

## Banda magnética

Con `evdev` (lectores HID que "teclean" el swipe) o `pyserial` (lectores serie), extra `[msr]`.

```sh
emvy -r msr track --read       # lee un swipe del lector MSR
```

---

## BomberCat (Electronic Cats, RP2040)

Placa versátil por USB serie: lector EMV contactless, passthrough APDU, magspoof, relay NFC y
**emulación** de tag NDEF o de tarjeta EMV (para perfilar/fuzzear terminales). Extra `[bombercat]`.

```sh
emvy bombercat setup                 # prepara el framework oficial (venv aislado)
emvy bombercat read --save cap1      # lee EMV contactless → captura
emvy -r bombercat discover|apdu|info # úsalo como cualquier lector
emvy bombercat fw list               # firmwares oficiales (UF2)
emvy bombercat fw flash NFCGate      # descarga + flashea (bootloader UF2)
```

### Firmware

- **Oficiales prebuilt** (`.uf2`): se flashean por bootloader UF2 (reset 1200-bps → unidad `RPI-RP2`;
  si no entra solo, doble-tap RESET). Recuperable vía BOOTSEL.
- **Firmware unificado EMVy** (`firmware/EMVyBomberCat/`): EMV + passthrough + tags + magspoof +
  emulación NDEF/EMV. Se **compila** con `arduino-cli` y se **sube por picotool**
  (`arduino-cli upload`, **no** por `.uf2` — el `.uf2` a `RPI-RP2` es solo para las imágenes
  oficiales).

### Gotchas conocidos en Linux

- **Regla udev para subir firmware**: `arduino-cli upload` / picotool puede fallar con "try sudo or
  check your permissions". Solución:

  ```sh
  echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="2e8a", MODE="0666"' | \
    sudo tee /etc/udev/rules.d/99-pico.rules
  sudo udevadm control --reload-rules --trigger
  ```

- **Identificación USB**: un BomberCat genuino puede enumerar como
  `2341:005e Arduino SA Nano RP2040 Connect` por un bug de packaging del core
  `electroniccats:mbed_rp2040` v2.0.0. Es **cosmético**; el mapeo de pines (IRQ=11/VEN=13 del PN7150)
  es correcto. Detalle completo en `CLAUDE.md §12`.

Para el detalle de la emulación NDEF/EMV observable, los comandos serie y el relay NFC, ver
`CLAUDE.md §9`.
