# Changelog

Todas las versiones notables de EMVy Controller. El formato sigue, a grandes rasgos,
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); el proyecto está en **BETA**, por lo que
la API y los formatos pueden cambiar entre versiones menores.

## [0.5.0-beta] — 2026-09-13

Primera publicación pública (BETA).

### Añadido
- **Núcleo puro** (`emvy/core/`): parseo/encoding BER-TLV, APDU/`Transceiver`, tags EMV, AIDs, ATR,
  flujo EMV (discover/select/GPO/AFL/records/GET DATA), pistas de banda magnética, NDEF, y análisis
  de seguridad (AIP/AUC, CVM, ODA con verificación RSA del certificado del emisor).
- **Lectores** (`emvy/readers/`): backends PC/SC, NFC (nfcpy), banda magnética (evdev/pyserial) y
  **BomberCat** (serie), todos tras la abstracción `Transceiver`, con degradación elegante.
- **Proyectos y variables**: espacios de trabajo persistentes, perfil de terminal EMV, variables
  libres, alias amistosos y perfiles de terminal preconfigurados.
- **Interfaces**: **TUI** (Textual), **GUI** de escritorio (PySide6/Qt) con paridad de funciones, y
  **CLI** para scripting.
- **Escritura y fuzzing**: UPDATE RECORD/BINARY, PUT DATA, APPEND; plantillas de banda mutada
  (magspoof), registros EMV mutados y tags NDEF malformados para probar terminales/POS.
- **BomberCat**: lector EMV contactless, passthrough APDU, magspoof, **emulación de tag NDEF** y de
  **tarjeta EMV** (perfilado de terminales), escaneo a RAM, y flasheo de firmware (arduino-cli /
  bombercat-tools). Firmware unificado en `firmware/EMVyBomberCat/`.
- **Pagos** (`emvy/payments/`): modelo `EmvCard`, codec ISO 8583 (con campo 55 EMV y traductor
  legible), análisis de criptograma (replay ATC/ARQC) y cliente de switch/adquirente.
- **Framework de PoCs** (`emvy/poc/`): runner + plugins por proyecto + plantillas ISO 8583
  (sign-on / compra / reverso), con evidencia automática, dry-run y modo solo-lectura.
- **Empaquetado**: build de **AppImage** (Linux) y `.exe` (Windows) de la GUI vía PyInstaller.
- **Pruebas**: suite offline de 238 tests con tarjeta y serial simulados (sin hardware).

### Notas
- Publicado como **BETA**: la CLI, la API interna y los formatos de datos pueden cambiar.
- Solo se distribuyen binarios de **Linux** (AppImage) en las releases; Windows es best-effort desde
  el código.

[0.5.0-beta]: https://github.com/Glitchboi-sudo/EMVy_Controller/releases/tag/v0.5.0-beta
