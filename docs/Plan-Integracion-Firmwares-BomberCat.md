# Plan de integración de firmwares BomberCat en la GUI

**Estado:** En ejecución — v1.1 · Sesiones 1–5 completas + **refactor ADR-001 aplicado**
(2026-09-18, ver §10 Progress log) · queda pendiente §7.2 (streaming genérico watch/monitor/scan)
como transversal ·
**Giro arquitectónico ADR-001 (2026-09-17): un Tab de nivel superior por firmware** (supersede los
sub-tabs de §5.1; **refactor ya ejecutado** — los seis paneles (Dispositivo/Tags/Readers/Magspoof/
Mifare/Relay) son ya Tabs propios)
**Alcance:** exponer en la GUI de escritorio (`emvy/gui/`) las funciones específicas de cada
firmware oficial de BomberCat, orquestadas a través del CLI vendorizado
`vendor/bombercat-tools/` desde `emvy/integrations/bombercat_tools.py`.
**Fuera de alcance (temporal):** el firmware **EMV** propio (`firmware/EMVyBomberCat`,
`firmware/bombercat_emv_reader`) y su ruta passthrough/emulación. Queda **incompatible**
mientras dure esta integración; no se toca `emvy/readers/bombercat.py` salvo lo indicado en §8.
**Audiencia:** desarrolladores que ejecutarán este plan en sesiones posteriores.

> Written for: desarrolladores del repo que implementarán la integración firmware↔GUI en
> sesiones futuras; asume familiaridad con `emvy/gui/` y con el CLI de `bombercat-tools`.

> Entorno virtual de prueba en: `source ~/GUIBombercat/bin/active`

---

## 0. TL;DR

Hoy la pestaña **BomberCat** de la GUI (`emvy/gui/panels/firmware.py`) solo compila/sube los
sketches locales de `firmware/` con `arduino-cli`. **No** expone ninguna de las funciones de los
firmwares oficiales (leer tags, detectar lectores, Mifare, magspoof, relay NFCGate) ni el flasheo
de imágenes `.uf2` oficiales, pese a que el orquestador `bombercat_tools.py` **ya tiene** los
helpers de bajo nivel (`devices`, `status`, `fw_list`, `flash_capture`, `tags_read`,
`readers_read`, `setup_env_gui`).

El trabajo es, esencialmente, **cablear lo que ya existe** y **completar los helpers que faltan**
(mifare, magspoof, relay) siguiendo el patrón `GUI → MainWindow (submit/worker) → bombercat_tools →
subprocess(vendor CLI) → firmware`. La estrategia de autoflasheo es **explícita y dirigida por la
GUI** (nunca implícita): EMVy fija `BOMBERCAT_AUTO_FLASH=never` a propósito (ver §6).

---

## 1. Arquitectura de referencia (la que este plan sigue)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  GUI  (emvy/gui/panels/*.py)  — solo widgets + señales, nada bloqueante    │
│    · dispara acción → llama a un método de MainWindow                      │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  self.win.<accion>()   (métodos de emvy/gui/app.py)
┌───────────────▼──────────────────────────────────────────────────────────┐
│  MainWindow (emvy/gui/app.py)  — orquestación por señales Qt              │
│    · submit(self.pool, fn, on_result=…, on_line=…, on_error=…)  (worker)   │
│    · emite notify / *_event a la consola cruda                             │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  fn = bombercat_tools.<helper>   (corre en QThreadPool)
┌───────────────▼──────────────────────────────────────────────────────────┐
│  Orquestador (emvy/integrations/bombercat_tools.py)  — subprocess aislado │
│    · _base_cmd(root) = [venv_python, "bombercat.py"]                       │
│    · run_capture / run_json / run_passthrough  (+ _env fija AUTO_FLASH)    │
└───────────────┬──────────────────────────────────────────────────────────┘
                │  subprocess contra vendor/bombercat-tools/.venv
┌───────────────▼──────────────────────────────────────────────────────────┐
│  vendor/bombercat-tools  (CLI click/rich)  → USB-serie → firmware         │
└──────────────────────────────────────────────────────────────────────────┘
```

> **Nota de navegación (ADR-001):** el diagrama de capas (GUI→MainWindow→orquestador→vendor)
> **no cambia**. Lo que cambia es **cómo se agrupa la superficie de UI**: cada firmware pasa de
> ser un *sub-tab* dentro de un único panel "BomberCat" a ser un **Tab de nivel superior propio**.
> Ver la decisión completa en la sección **ADR-001** justo debajo.

**Reglas invariantes** (respetarlas en toda la implementación):

- La GUI **nunca** llama `subprocess` ni `bombercat_tools` directamente desde un panel: siempre a
  través de un método de `MainWindow` que use `submit(...)` (worker en `QThreadPool`). Tocar
  widgets desde el hilo de trabajo está prohibido — solo señales (ver `emvy/gui/worker.py`).
- El orquestador **captura** salida (no hereda stdout): la GUI no tiene TTY. Usar `run_capture` /
  `run_json`, nunca `run_passthrough` desde la GUI (ese es para la CLI interactiva).
- El orquestador corre contra el **venv aislado** de `bombercat-tools` (`ensure_venv`), no el de
  EMVy — no mezclar dependencias.

---

## ADR-001 — Un Tab de nivel superior por firmware (supersede los sub-tabs de §5.1)

**Estado:** Aceptada (2026-09-17). **Supersede:** el diseño de sub-tabs internos descrito en §5.1
y entregado por las Sesiones 1–3 (ver §10). **Afecta:** §2.1, §5.1, §5.2, §7 (hoja de ruta),
`emvy/gui/app.py`, `emvy/gui/panels/firmware.py`, `tests/test_gui.py`.

### Contexto

El panel BomberCat se diseñó cuando la GUI orquestaba **un solo firmware** (el EMV propio,
`EMVyBomberCat`). Al incorporar los firmwares **oficiales** (DetectTags, DetectReaders,
MifareClassic, magspoof, NFCGate) —cada uno ya expuesto en el CLI vendorizado— las Sesiones 1–3
los fueron colgando como **sub-tabs** de un `QTabWidget` interno (`FirmwarePanel._sub`,
`emvy/gui/panels/firmware.py:69`), gated por capacidad. Hoy la navegación real es de **dos
niveles**: barra lateral → grupo `HARDWARE` → único ítem **BomberCat** (`app.py:187`) →
sub-tabs *Dispositivo/Flashear/Tags/Readers/Magspoof* (y las pendientes *Mifare/Relay*).

### Decisión

**Cada firmware es un Tab de nivel superior propio**, expuesto como un ítem independiente del
grupo `HARDWARE` de la barra lateral, en paridad con el resto de pestañas de la app (Lectores,
Cobros, PoC…). El único panel "BomberCat" con sub-tabs deja de existir; en su lugar hay:

- un panel **Dispositivo/Flashear** (control-plane común: `device list`, `status`, `identify`,
  permisos udev, flasheo de imágenes oficiales + compilar firmware propio), y
- **un panel por firmware/capacidad**: *Tags*, *Readers*, *Mifare*, *Magspoof*, *Relay NFCGate*
  (y, cuando EMV vuelva al alcance —§8—, también EMVY).

### Justificación (por qué sub-tabs → Tabs independientes)

1. **El sistema ya no gira en torno a un firmware.** EMVY es ahora **uno más** entre varios
   firmwares intercambiables. Un panel único con EMVY implícito como "el firmware" ya no modela
   la realidad; cada firmware es un **modo/herramienta distinto**, no una faceta de uno solo.
2. **Descubribilidad.** Con sub-tabs, cada función queda enterrada a **dos niveles** (sidebar →
   BomberCat → sub-tab). Como Tabs de primer nivel aparecen directamente en la barra lateral,
   igual que el resto de operaciones.
3. **El mismo problema de overflow que ya resolvimos arriba.** La app migró de 11 pestañas
   superiores a una **barra lateral agrupada** justamente para no desbordar la barra de pestañas
   (CLAUDE.md §5). Meter 7+ sub-tabs dentro de un panel reintroduce ese desbordamiento un nivel
   más abajo. La barra lateral **ya sabe agrupar** (`_NAV_GROUPS`): el grupo `HARDWARE` absorbe
   los firmwares sin límite práctico.
4. **Consistencia arquitectónica.** Todo lo demás en la GUI es un Tab de primer nivel conducido
   por la barra lateral. Los firmwares merecen la misma paridad; un `QTabWidget` anidado es una
   excepción que complica el modelo (`self.tabs` es la API única de pestañas, `app.py:122`).
5. **Aislamiento de estado y gating más limpio.** Habilitar/deshabilitar un **Tab entero** por
   capacidad (el board corre una imagen a la vez) es más natural que habilitar sub-tabs sueltos
   dentro de un panel que, por definición, casi siempre tendría la mayoría deshabilitados.

### Consecuencias

- **Positivas:** navegación plana y consistente; cada firmware evoluciona en su propio módulo/
  archivo sin tocar a los demás; el gating se expresa a nivel de ítem de barra lateral; EMVY
  encaja sin trato especial cuando vuelva.
- **Coste:** hay que **refactorizar** lo entregado en Sesiones 1–3 (mover cada `_build_*_tab`
  a su panel) y **actualizar los tests** de GUI que asumen sub-tabs. Es refactor mecánico
  (mover, no reescribir la lógica de cada sub-tab). Ver §5.1 (marcada como superseded) para el
  detalle de qué se mueve, y "Recomendación de refactor" (debajo) para el plan paso a paso.

### Implicaciones en el repo y archivos clave

**`emvy/gui/app.py`** (wiring de navegación):
- `_NAV_GROUPS` (`app.py:168`): el grupo `HARDWARE` pasa de `(("BomberCat", "cpu"),)` a **un ítem
  por firmware** —p.ej. `("Dispositivo","cpu"), ("Tags","nfc"), ("Readers","plug"),
  ("Mifare","square"), ("Magspoof","credit-card"), ("Relay","shield")`— cada uno con su icono SVG.
  **Ojo:** `emvy/gui/icons.py` hoy solo define `{cpu, credit-card, download, flask, folder, home,
  nfc, play, plug, search, shield, sliders, square, wrench, zap}`; para iconos más específicos
  (tag/radio/key/wifi) hay que **añadir el SVG inline** a `icons.py` primero, o reutilizar los
  existentes de arriba.
- `self.tabs.addTab(...)` (`app.py:110-120`): un `addTab` por panel de firmware en vez del único
  `addTab(self.firmware_panel, "BomberCat")`. El mapeo `_nav_to_tab` funciona solo (une por
  etiqueta, `app.py:199`), no hay que tocarlo.
- `_CONSOLE_TABS` (`app.py:154`): sustituir `"BomberCat"` por **cada** etiqueta de firmware que
  emita tráfico serie (Dispositivo, Tags, Readers, Mifare, Magspoof, Relay), para que la consola
  cruda siga apareciendo en ellas.
- Métodos de `MainWindow` (`refresh_device`, `flash_image`, `tags_read`, `readers_read`,
  `magspoof_*`…): hoy referencian `self.firmware_panel`. Deben **direccionar el panel concreto**
  (o recibir el panel emisor como argumento / usar `self.sender()`), ya que dejará de haber un
  único `firmware_panel`.

**`emvy/gui/panels/firmware.py`** (superficie de UI):
- Desaparece el `QTabWidget` interno `self._sub` (`firmware.py:69`) y `register_gated`/
  `_apply_gating` como mecanismo *intra-panel*. El gating sube a nivel de Tab/ítem de sidebar.
- Los cuerpos `_build_device_tab`/`_build_flash_tab`/`_build_tags_tab`/`_build_readers_tab`/
  `_build_magspoof_tab` (`firmware.py:95-343`) se **extraen a paneles propios** (un archivo o
  clase por firmware), reutilizando su lógica tal cual.
- El estado que hoy es compartido dentro del panel (`self._port`/`port()`, `self.caps`,
  `self._log`, `log`/`log_result`) debe **centralizarse** (ver "Integración a mantener").

### Recomendación de refactor (cómo llevarlo a cabo)

1. **Base común compartida.** Extraer una `BaseFirmwarePanel(QWidget)` (o un pequeño controlador
   inyectado) que aporte: `capability: str` (la capacidad que habilita el panel), acceso al
   **puerto** compartido, `set_status(st)` que se auto-gatea (`enabled = capability in st.caps`),
   y `log`/`log_result`. Cada panel de firmware hereda de ella y solo implementa su UI + sus
   acciones. Es el equivalente a `register_gated`, pero por panel.
2. **Control-plane aparte.** `Dispositivo/Flashear` es un panel **siempre habilitado** (no tiene
   `capability`); es el **único** que flashea y refresca `status`. Absorbe el compilar-local
   actual como sección secundaria (igual que hoy, §5.1).
3. **Mover 1:1.** Cada `_build_<x>_tab` actual → `class <X>Panel(BaseFirmwarePanel)`; su
   `capability` = la que hoy pasa a `register_gated`. La lógica de render (`show_tag`,
   `show_reader`, `show_magspoof`, `show_cards`, `_kv_table`…) viaja con su panel.
4. **Fuente única de caps.** `MainWindow` mantiene el último `status_json()` y, tras cualquier
   flasheo (`_on_flash_done`) o "Refrescar", hace **broadcast** de `set_status(st)` a **todos**
   los paneles de firmware → todos re-gatean a la vez. Esto reemplaza el `_apply_gating` interno.
5. **EMVY como un panel más.** Cuando EMV vuelva al alcance (§8), su UI es otro
   `<EmvPanel>(BaseFirmwarePanel)` con `capability="emv"`; sin trato especial.
6. **Tests.** Actualizar `tests/test_gui.py`: los que hoy asertan la lista de sub-tabs de
   `FirmwarePanel._sub` (`test_firmware_subtabs_and_status_gating`) pasan a asertar los **Tabs de
   nivel superior** presentes en `self.tabs` + el gating **por panel** (`set_status` habilita/
   deshabilita el Tab correcto). Los renderizadores (`show_tag`/`show_reader`/`show_magspoof`/
   `show_cards`) se prueban sobre su nuevo panel, sin cambios de lógica.

### Integración/dependencias a mantener entre Tabs

El board corre **una** imagen a la vez y tiene **un** puerto serie: separar los firmwares en Tabs
**no** debe fragmentar ese estado compartido. Debe seguir centralizado:

- **Puerto serie único.** No duplicar un selector de puerto por panel. Un único origen (en
  `MainWindow` o en el control-plane) que todos los paneles **leen** (`port()`). Un board = un
  puerto.
- **Status/capacidades compartidas + re-gating global.** Como solo hay una capacidad activa a la
  vez, tras cada flasheo **todos** los paneles deben re-evaluar su habilitación desde el mismo
  `status`. Mantener un único broadcast de caps (punto 4 del refactor). En la práctica, solo el
  Tab cuya capacidad está presente queda **habilitado**; los demás muestran la CTA
  "Flashear <imagen> para habilitar" (§6) — esa UX se conserva, solo cambia de sub-tab a Tab.
- **Consola cruda compartida.** El dock inferior y sus señales `apdu_event`/`wire_event` viven en
  `MainWindow` (`app.py:57-58`); cada Tab de firmware que haga IO serie debe estar en
  `_CONSOLE_TABS`. La consola es transversal, no per-panel.
- **Orquestador único.** Todos los paneles siguen pasando por `bombercat_tools` vía
  `submit(...)` de `MainWindow` (nunca subprocess directo). Las reglas invariantes de §1 no cambian.
- **Flasheo dirigido (§6) intacto.** El control-plane sigue siendo el **único escritor** de
  firmware; un panel de firmware que pida habilitarse dispara `flash_image(image_for_capability(
  cap))` **a través del camino común**, que al terminar refresca status y re-gatea a todos.

---

## 2. Análisis de la GUI actual

### 2.1 Estructura de navegación (`emvy/gui/app.py`)

- `MainWindow` monta 11 paneles en un `QTabWidget` con la barra oculta; la navegación real es el
  `QListWidget#nav` agrupado (`_NAV_GROUPS`, `emvy/gui/app.py:167`). Grupos actuales:
  `SESIÓN` · `TARJETA` · `OPERACIONES` · `HARDWARE`.
- El único ítem de **HARDWARE** es **BomberCat** (`("BomberCat", "cpu")`), que apunta al
  `FirmwarePanel` (`emvy/gui/app.py:107,119`). **→ ADR-001 lo reemplaza por un ítem por firmware.**
- La **consola cruda** (dock inferior) se muestra solo en `_CONSOLE_TABS` (`emvy/gui/app.py:154`),
  que **ya incluye** `"BomberCat"`. Cualquier tráfico serie que emitamos por `wire_event`/
  `apdu_event` aparecerá ahí sin trabajo extra.

### 2.2 El panel BomberCat actual (`emvy/gui/panels/firmware.py`)

Hace **solo dos cosas**, ambas vía `emvy/integrations/arduino.py` (no vía `bombercat_tools`):

| Acción | Widget | Método de `MainWindow` | Backend |
|---|---|---|---|
| Compilar sketch local | botón "Compilar" | `compile_firmware(dir, upload=False)` (`app.py:830`) | `arduino.compile_sketch` |
| Compilar + subir (picotool) | botón "Compilar y subir" | `compile_firmware(dir, upload=True, port)` | `arduino.upload_sketch` |
| Permisos USB (udev) | botón "Permisos USB (udev)…" | `setup_udev()` (`app.py:852`) | `bombercat_tools.setup_env_gui` |

**Conclusión:** el panel está orientado a *desarrollo de firmware propio*, no a *operar los
firmwares oficiales*. La integración de este plan es **aditiva** y en su mayor parte **nueva
superficie de UI**, no reescritura.

### 2.3 Puntos de entrada reutilizables (ya existen)

- **Worker/threads:** `submit(pool, fn, *, on_result, on_error, on_line, want_progress)`
  (`emvy/gui/worker.py:74`). Si `fn` acepta `progress`, se le inyecta un callable que emite líneas
  → ideal para el streaming de `flash`/`monitor`/`watch`.
- **Notificaciones:** `self.win.notify.emit("...")` → barra de estado.
- **Consola cruda:** señales `apdu_event` / `wire_event` (`app.py:57-58`) ya conectadas al dock.
- **Patrón de referencia ya cableado:** `compile_firmware` y `setup_udev` (`app.py:830-869`) son la
  plantilla exacta a copiar para cada nueva acción de firmware.

### 2.4 Flujo de datos GUI → firmware (traza concreta, ejemplo `tags read`)

```
FirmwarePanel  →  win.tags_read(timeout)                       # nuevo método MainWindow
             →  submit(pool, bombercat_tools.tags_read, timeout, on_result=panel.show_tag)
             →  bombercat_tools.tags_read()                     # YA EXISTE
             →  run_json(["tags","read","--json","-t",str(timeout)])
             →  subprocess [venv]/bombercat.py tags read --json # vendor CLI
             →  DetectTags.uf2 sobre PN7150 → :tag … → JSON
             →  dict {"uid":…, "tech":…, …} vuelve por señal result → widget
```

---

## 3. Mapa firmware ↔ capacidad ↔ CLI ↔ orquestador ↔ GUI (matriz maestra)

Fuente de verdad de capacidades: `vendor/bombercat-tools/modules/core/firmwares.py`
(`CAP_*`, registro `_ENTRIES`) y `.../requirements.py` (`CAPABILITY_PROVIDER`).

| Firmware (`.uf2`) | Capacidad (`CAP_*`) | Subcomandos CLI relevantes | Helper en `bombercat_tools.py` | Estado helper | Punto GUI propuesto |
|---|---|---|---|---|---|
| **DetectTags** | `tags` | `tags read/watch/scan/info` | `tags_read(timeout)` | ✅ existe | Sub-tab *Tags* |
| **MifareClassic** | `mifare` | `tags mifare keys/check/dump/restore/auth/read/write/sector` | `mifare_*` | ❌ **falta** | Sub-tab *Mifare* |
| **DetectReaders** | `readers` | `readers read/watch/scan/info` | `readers_read(timeout)` | ✅ existe | Sub-tab *Readers* |
| **magspoof** | `magspoof` | `magspoof play/show/watch/info`, `magspoof card add/list/select/del/get/set`, `magspoof nfc/visa/read` | `magspoof_*` | ❌ **falta** | Sub-tab *Magspoof* |
| **NFCGate** | `relay`,`config`,`capture` | `relay config wifi/nfcgate/show`, `relay run/stop/status/monitor`, `capture start` | `relay_*`, `capture_*` | ❌ **falta** | Sub-tab *Relay NFCGate* |
| *(todos)* | — control plane | `device list`, `status`, `identify`, `flash`, `flash --list`, `setup-env` | `devices`, `status_text`, `fw_list_names`, `flash_capture`, `setup_env_gui` | ✅ existe | Barra superior común |

> **Nota de exclusividad:** `MifareClassic` **no** declara `CAP_TAGS` a propósito (ver comentario
> en `firmwares.py`), aunque emita `:tag`. No mezclar los sub-tabs Tags y Mifare.

### 3.1 Subcomandos exactos (verificados en `vendor/bombercat-tools/modules/`)

- **tags** (`modules/tags/`): `read`, `watch`, `scan`, `info`, `code`, y el grupo `mifare` con
  `keys`, `check`, `dump`, `restore`, `auth`, `read`, `write`, `write-text`, `sector`.
- **readers** (`modules/readers/`): `read`, `watch`, `scan`, `info`.
- **magspoof** (`modules/magspoof/`): `play`, `show`, `watch`, `info`, `nfcinfo`, `selres`,
  `normalize-sc`, `require-sc`, y grupos `card` (`add`/`list`/`select`/`del`/`get`/`set`) y
  `nfc`/`visa`/`read`.
- **relay + capture** (`modules/nfcgate/`, `modules/capture/`): `relay config {wifi,nfcgate,show}`,
  `relay {run,stop,status,monitor}`, `capture start`.

---

## 4. Estado del orquestador (`emvy/integrations/bombercat_tools.py`)

### 4.1 Lo que YA existe (reutilizar tal cual)

- Infra: `locate()`, `venv_ready()`, `ensure_venv()`, `_base_cmd()`, `_env()` (fija
  `BOMBERCAT_AUTO_FLASH=never`, `NO_COLOR`, `TERM=dumb`).
- Ejecución: `run_passthrough()` (CLI), `run_capture()` (GUI/TUI), `run_json()` + `_extract_json()`.
- Helpers de alto nivel: `version()`, `devices()`, `status()/status_text()`, `fw_list()/
  fw_list_names()`, `parse_fw_names()`, `flash()/flash_capture()`, `devices_text()`,
  `tags_read()`, `readers_read()`, `setup_env_passthrough()`, `setup_env_gui()`.

### 4.2 Lo que FALTA (implementar en este plan)

Todos siguen el patrón `run_json(...)` (si el subcomando tiene `--json`) o `run_capture(...)`
(salida rica → parsear/mostrar como texto). Firmas propuestas (estables, no cambiarlas después):

```python
# --- estado/capacidad (nuevo, base del autoflasheo dirigido) ---------------
def status_json(port=None, timeout=30) -> dict: ...        # parsea `status` → {fw_name, caps,…}
def capability_present(cap: str, *, port=None) -> bool: ... # status_json → cap in caps

# --- Mifare (MifareClassic.uf2) --------------------------------------------
def mifare_keys(timeout=20) -> list[str]: ...                       # tags mifare keys
def mifare_check(out_keyfile, timeout=60) -> subprocess.CompletedProcess: ...  # tags mifare check -o
def mifare_dump(keys_file, out_json, timeout=90): ...              # tags mifare dump --keys-file --out
def mifare_restore(dump_json, timeout=90): ...                     # tags mifare restore --dump

# --- magspoof (magspoof.uf2) -----------------------------------------------
def magspoof_show(timeout=20) -> dict: ...                         # magspoof show (--json si existe)
def magspoof_play(timeout=20): ...                                 # magspoof play
def magspoof_card_list(timeout=20) -> list[dict]: ...              # magspoof card list
def magspoof_card_add(name, *, t1=None, t2=None): ...              # magspoof card add <name> --t1 --t2
def magspoof_card_select(name): ...                                # magspoof card select <name>
def magspoof_nfc_visa(timeout=30): ...                             # magspoof nfc visa

# --- relay NFCGate (NFCGate.uf2) -------------------------------------------
def relay_config_wifi(ssid, password, *, device_id=None): ...      # relay config wifi
def relay_config_nfcgate(server, session, role, *, device_id=None): ...  # relay config nfcgate
def relay_config_show(*, device_id=None) -> dict: ...              # relay config show
def relay_run(*, device_id=None): ...                              # relay run
def relay_stop(*, device_id=None): ...                             # relay stop
def relay_status(*, device_id=None) -> dict: ...                   # relay status
def capture_start(*, wireshark=False, on_line=None): ...           # capture start (streaming)

# --- capacidad → imagen (espejo de requirements.CAPABILITY_PROVIDER) --------
CAPABILITY_IMAGE = {                     # NO importar del vendor: duplicar aquí y testear igualdad
    "tags": "DetectTags", "readers": "DetectReaders",
    "mifare": "MifareClassic", "magspoof": "magspoof",
    "relay": "NFCGate", "config": "NFCGate", "capture": "NFCGate",
}
def image_for_capability(cap: str) -> str: return CAPABILITY_IMAGE[cap]
```

> **Antes de implementar cada helper:** confirmar con
> `[venv]/bombercat.py <cmd> --help` si el subcomando ofrece `--json` (usar `run_json`) o solo
> salida rica (usar `run_capture` + parser dedicado, como `parse_fw_names`). No asumir `--json`.
> `watch`/`monitor`/`scan -t` son **streaming largo**: se implementan con `run_capture(timeout=…)`
> o, mejor, con una variante que emita líneas por `progress` (ver §7.2).

---

## 5. Puntos de integración GUI → orquestador → firmware

### 5.1 Rediseño del panel BomberCat (dos responsabilidades separadas)

> ⚠️ **SUPERSEDED por ADR-001.** Este diseño de **sub-pestañas** fue el vigente en Sesiones 1–3
> (entregado, ver §10) y se conserva aquí como referencia histórica y como mapa de "qué se mueve"
> al refactorizar. El diseño **vigente** es **un Tab de nivel superior por firmware** — leer
> ADR-001. La correspondencia es directa: cada sub-tab de abajo pasa a ser un panel/Tab propio.

El panel actual mezcla "compilar firmware propio" con lo que será "operar firmware oficial".
Proponer **sub-pestañas** dentro del panel BomberCat (patrón ya usado en Fuzzing, CLAUDE.md §5):

```
BomberCat
├── Dispositivo   (común)   device list · status → firmware+capacidades · identify · Permisos USB
├── Flashear      (común)   flash --list → combo · Flashear <imagen> (streaming) · [Compilar local]
├── Tags          (gated:tags)     read/watch/scan → tabla de UID
├── Readers       (gated:readers)  read/watch/scan → tabla de lectores
├── Mifare        (gated:mifare)   keys · check → keyfile · dump → JSON · restore
├── Magspoof      (gated:magspoof) show · play · card list/add/select · nfc visa
└── Relay NFCGate (gated:relay)    config wifi/nfcgate · run/stop/status · capture start
```

- **"gated:X"** = el sub-tab se **habilita/deshabilita** según `status_json().caps`. Si la placa no
  trae la capacidad, el sub-tab muestra un botón **"Flashear <imagen> para habilitar"** que dispara
  el flasheo explícito (§6). El sub-tab *Dispositivo* siempre está activo.
- El sub-tab **Flashear** absorbe el compilar-local actual como sección secundaria ("Firmware
  propio (dev)") para no perder esa función; la primaria pasa a ser flashear imágenes oficiales.

### 5.2 Nuevos métodos en `MainWindow` (uno por acción, patrón `compile_firmware`)

Cada uno: `self.firmware_panel.log("→ …")` + `submit(self.pool, bt.<helper>, …, on_result=…,
on_error=lambda m: self.notify.emit(...))`. Lista mínima:

```
refresh_device()      → bt.status_json         → actualiza cabecera + habilita sub-tabs
flash_image(name)     → bt.flash_capture(name) → want_progress=True, on_line→log (streaming)
identify_device()     → bt.run_capture(["identify"])
tags_read()/readers_read()   → ya hay helper; solo el método MainWindow + render de tabla
mifare_check()/mifare_dump()/mifare_restore()
magspoof_show()/magspoof_play()/magspoof_card_*()/magspoof_nfc_visa()
relay_config()/relay_run()/relay_stop()/relay_status()/capture_start()
```

### 5.3 Contrato de datos GUI↔orquestador

- Los helpers `*_json`/`*_read` devuelven `dict`/`list[dict]` → el panel los pinta en
  `CopyableDataTable`/labels. **No** pasar objetos del vendor (viven en otro venv/proceso): solo
  tipos JSON planos cruzan la frontera del subprocess.
- Los helpers de acción sin datos devuelven `subprocess.CompletedProcess` → el panel usa
  `log_result(res)` (ya existe en `firmware.py`) para volcar rc/stdout/stderr.
- Errores: el orquestador lanza `BombercatToolsError` con el `tail` del stderr/stdout (incluye los
  mensajes de *mismatch de firmware* de v1.3.0) → llega a `on_error` → `notify`.

---

## 6. Estrategia de autoflasheo (dirigida por la GUI, explícita)

**Decisión de diseño (mantener):** EMVy fija `BOMBERCAT_AUTO_FLASH=never` en `_env()`
(`bombercat_tools.py`). Razón documentada: por subprocess con stdout capturado, un `ASK` dejaría un
prompt de confirmación **invisible** bloqueado en stdin. Por tanto **no** delegamos el autoflasheo
al orquestador del vendor (`ensure_firmware`); lo hacemos **explícito desde la GUI**:

```
1. Usuario abre un sub-tab firmware-específico (p.ej. Mifare).
2. GUI ya tiene status_json().caps (refrescado al entrar al panel / botón Refrescar).
3. Si "mifare" ∈ caps → sub-tab operativo.
   Si NO → sub-tab muestra: "Esta placa corre <fw>. Mifare necesita MifareClassic.
           [Flashear MifareClassic]"  (QMessageBox de confirmación antes de escribir).
4. Al confirmar → flash_image(image_for_capability("mifare")) con streaming en el log.
5. Tras flashear → refresh_device() (re-lee status) → habilita el sub-tab.
```

- El mapeo capacidad→imagen se **duplica** en `bombercat_tools.CAPABILITY_IMAGE` (§4.2) en vez de
  importarlo del vendor (otro venv). Un test debe asertar que coincide con
  `requirements.CAPABILITY_PROVIDER` leyéndolo por subprocess, para que no deriven.
- **Confirmación obligatoria**: flashear reescribe toda la imagen y **borra** la config guardada
  (crítico para NFCGate: WiFi/relay). El diálogo debe advertirlo (mismo texto que
  `ensure_firmware._mismatch_message`).
- **Compilar/subir firmware propio** (arduino-cli, picotool) sigue igual y **separado** del flasheo
  de imágenes oficiales (UF2 vía `bombercat flash`). No confundir las dos rutas (CLAUDE.md §12).

---

## 7. Hoja de ruta por sesiones (con prioridades)

Cada sesión deja tests verdes (`.venv/bin/python -m pytest tests/ -q`) y GUI verificable headless
(`QT_QPA_PLATFORM=offscreen`, `QWidget.grab()`, ver `tests/test_gui.py`).

### Sesión 1 — Cimientos: Dispositivo + Flashear + gating (PRIORIDAD ALTA)
- Orquestador: `status_json`, `capability_present`, `CAPABILITY_IMAGE`, `image_for_capability`.
- GUI: reestructurar `FirmwarePanel` en sub-tabs; implementar sub-tab **Dispositivo**
  (`device list`, `status`→cabecera con fw+caps, `identify`, botón "Permisos USB" ya existe) y
  sub-tab **Flashear** (combo desde `fw_list_names`, botón flashear con streaming, sección dev).
- `MainWindow`: `refresh_device`, `flash_image`, `identify_device`.
- Autoflasheo dirigido (§6) como mecanismo genérico de habilitación de sub-tabs.
- Tests: `status_json` con `fakeserial`/salida canned; test GUI de humo del panel; test de igualdad
  `CAPABILITY_IMAGE` ↔ `CAPABILITY_PROVIDER`.

### Sesión 2 — DetectTags + DetectReaders (PRIORIDAD ALTA, helpers ya existen)
- GUI: sub-tabs **Tags** y **Readers** (botón read/scan → `CopyableDataTable`; `watch` en §7.2).
- `MainWindow`: métodos `tags_read`, `readers_read` (helpers `bt.tags_read/readers_read` ya listos).
- Bajo esfuerzo/alto valor: es casi solo UI + render de JSON.

### Sesión 3 — magspoof (PRIORIDAD MEDIA)
- Orquestador: `magspoof_show/play/card_list/card_add/card_select/nfc_visa`.
- GUI: sub-tab **Magspoof** (inspección + store de tarjetas + play). Reutilizar los editores de
  Track1/Track2 que ya existen en el panel Fuzzing donde aplique.
- Tests con `fakeserial` (emular respuestas del REPL magspoof).

### Sesión 4 — Mifare (PRIORIDAD MEDIA)
- Orquestador: `mifare_keys/check/dump/restore`. `dump` produce un JSON de tarjeta → integrarlo como
  captura del proyecto (`store.import_capture`) si aplica.
- GUI: sub-tab **Mifare** (keys → check → keyfile → dump → JSON → restore). Flujo con archivos
  intermedios en el proyecto activo (`<proy>/artifacts/`).

### Sesión 5 — Relay NFCGate — ✅ COMPLETA (2026-09-18, ver §10)
- Orquestador: `relay_config_*`, `relay_run/stop/status`, `capture_run` (`capture_start` del plan
  original se implementó como `capture_run`: acotada por duración, ver desviaciones en §10).
- GUI: panel propio **Relay** (ADR-001, no sub-tab), config WiFi/servidor/sesión/rol, run/stop,
  status en vivo. El relay necesita **dos** peers y un `nfcgate-server`; es control-plane (sin
  APDUs por serie salvo al capturar). `-ws` (Wireshark en vivo) queda fuera de la GUI (§10).

### Sesión 6 — Streaming, pulido y consola (transversal)
- Variante de orquestador con emisión por líneas para `watch`/`monitor`/`scan`/`flash` (§7.2).
- Rutear las líneas serie a la **consola cruda** vía `wire_event` (ya conectada para "BomberCat").
- Iconografía SVG del sub-tab (`emvy/gui/icons.py`), textos en español, tema compartido.

### 7.1 Paridad TUI (posterior, no bloqueante)
Replicar los mismos helpers en la pestaña BomberCat de la TUI (`emvy/tui/screens/firmware.py`).
El orquestador es compartido, así que la TUI reusa `bombercat_tools.*` sin cambios: solo UI.

### 7.2 Nota técnica: streaming de comandos largos
`watch`/`monitor`/`flash`/`scan` no terminan solos. Implementar en el orquestador una variante que
lance el subprocess con `stdout=PIPE` y llame `progress(line)` por cada línea, cancelable
(matando el proceso al cerrar el sub-tab o pulsar "Detener"). En la GUI: `submit(..., want_progress=
True, on_line=panel.append)`. Modelo ya probado en `setup_env_gui`/`compile_firmware`.

---

## 8. Riesgos, dependencias y notas

- **EMV fuera de alcance:** no tocar `emvy/readers/bombercat.py` (passthrough EMV) ni los sketches
  `firmware/EMVyBomberCat`, `firmware/bombercat_emv_reader` salvo para **deshabilitar/ocultar** en
  la GUI las rutas EMV que dependan de firmware EMV mientras dure la incompatibilidad. Registrar en
  CLAUDE.md §9 que EMV está temporalmente inactivo.
- **Un solo firmware a la vez:** la placa corre **una** imagen. Operar dos capacidades de firmwares
  distintos exige reflashear entremedias. La UI debe dejarlo claro (cabecera "Firmware actual: X").
- **Pérdida de config al flashear:** flashear NFCGate sobre sí mismo borra WiFi/relay guardados;
  advertir siempre (§6). Ofrecer `relay config show` antes.
- **Permisos USB (udev):** el flasheo por picotool y el acceso serie requieren la regla udev de
  v1.3.0 (`setup-env`, ya cableado en "Permisos USB"). Documentar como prerrequisito de Sesión 1.
- **Venv del vendor:** `ensure_venv` bootstrapea `vendor/bombercat-tools/.venv` la primera vez
  (puede tardar). La GUI debe mostrar progreso (`want_progress=True`) en la primera acción.
- **`--json` no garantizado:** verificar por `--help` antes de asumirlo (§4.2). Donde no exista,
  escribir un parser dedicado y **testearlo** contra salida canned (como `parse_fw_names`).
- **Fijación de versión:** EMVy está clavado a `PINNED_TAG = "v1.3.0"` del submódulo. Si sube la
  versión del vendor, revisar que los subcomandos/flags de este plan sigan vigentes.

---

## 9. Referencias de código

- Orquestador: `emvy/integrations/bombercat_tools.py` (helpers, `_env`, `run_*`).
- GUI panel actual: `emvy/gui/panels/firmware.py`; wiring: `emvy/gui/app.py`
  (`_NAV_GROUPS`, `_CONSOLE_TABS`, `compile_firmware`, `setup_udev`); worker: `emvy/gui/worker.py`.
- Catálogo/capacidades del vendor: `vendor/bombercat-tools/modules/core/firmwares.py`,
  `.../requirements.py`, `.../ensure_firmware.py`.
- Superficie CLI (docs): `vendor/bombercat-tools/docs/commands/{tags,readers,magspoof,relay,flash,
  status,setup-env}.md`; descripciones de imágenes: `bombercat-firmware/descriptions.json`.
- Contrato de descubrimiento (handshake común a todos los firmwares):
  `docs/BomberCatControl-Discovery-Contract.md`.

---

## 10. Progress log

Registro cronológico de lo entregado por sesión. Cada entrada anota qué quedó hecho, dónde,
y las desviaciones/hallazgos respecto al plan para que la siguiente sesión no re-descubra.

### Sesión 1 — Cimientos: Dispositivo + Flashear + gating — ✅ COMPLETA (2026-09-17)

**Orquestador** (`emvy/integrations/bombercat_tools.py`):
- `parse_status(text) -> dict` — parser puro de la tabla rich de `bombercat status` →
  `{name, version, detected, capabilities:[...]}`. Maneja continuación de celda (valor
  partido en varias líneas) y descarta `—` (dim) en capacidades.
- `status_json(port=None, timeout=30) -> dict` — corre `status` (por `run_capture`) y parsea;
  lanza `BombercatToolsError` si no hay tabla (nada respondió).
- `capability_present(cap, *, port=None) -> bool`.
- `CAPABILITY_IMAGE` (dict duplicado del vendor) + `image_for_capability(cap)` (lanza
  `BombercatToolsError` para capacidades sin proveedor canónico, p.ej. `identify`).
- `identify(port=None, timeout=30) -> CompletedProcess`.

**GUI — panel reestructurado** (`emvy/gui/panels/firmware.py`):
- `FirmwarePanel` pasa a un `QTabWidget` interno (`self._sub`) con sub-tabs **Dispositivo** y
  **Flashear**; puerto serie compartido (`self._port` + `port()`) y `self._log` común.
- **Dispositivo**: cabecera con labels firmware/versión/detección/capacidades (seleccionables)
  + botones Refrescar estado · Identificar (LED) · Permisos USB (udev).
- **Flashear**: grupo "Imágenes oficiales" (combo `self._image` poblado por
  `reload_images()`→worker, botón Flashear) + grupo "Firmware propio (dev)" que **absorbe** el
  compilar/subir arduino-cli previo (`self._sketch` intacto).
- **Gating genérico**: `register_gated(cap, widget)` + `_apply_gating()` + `set_status(st)` —
  las sesiones 2-5 solo registran su sub-tab y se habilita/deshabilita por capacidad.
  `set_images()`/`set_status()` son los puntos de entrada desde `MainWindow`.

**GUI — MainWindow** (`emvy/gui/app.py`): `refresh_device` (→`_on_device_status`),
`identify_device`, `reload_flash_images`, `flash_image(name, *, port)` con **QMessageBox de
confirmación** (§6) y `_on_flash_done`→`refresh_device` para re-aplicar gating. Todo por
`submit(...)` en el `QThreadPool`.

**Tests** (`tests/test_bombercat_tools.py`, `tests/test_gui.py`):
- `parse_status`: tabla completa, capacidades vacías (`—`), y sin tabla.
- `image_for_capability` (+ capacidad desconocida) y `test_capability_image_matches_vendor`:
  compara `CAPABILITY_IMAGE` contra `requirements.CAPABILITY_PROVIDER` del vendor **por
  subprocess contra el venv del vendor** (ver hallazgo abajo); pasa (no se salta).
- GUI: `test_firmware_subtabs_and_status_gating` (sub-tabs + `set_status` + gating);
  `test_firmware_lists_sketches` sigue verde (API `reload()`/`_sketch` preservada).
- Suite completa: **187 passed, 12 skipped**.

**CLAUDE.md** §5: actualizada la descripción del panel `firmware` (sub-tabs + gating).

**Desviaciones y hallazgos respecto al plan:**
1. **`status` NO tiene `--json`** (verificado en el CLI del vendor v1.3.0): `status_json`
   parsea la tabla rich, no consume JSON. Confirma la advertencia de §4.2/§8.
2. **Flasheo sin streaming (diferido a Sesión 6):** el plan (§5.2) sugería `flash_image` con
   `want_progress=True`, pero `flash_capture` **no acepta** un kwarg `progress` (el worker lo
   inyectaría y reventaría con `TypeError`). Se usa `flash_capture` bloqueante + `log_result`
   al terminar. El streaming real (`stdout=PIPE`+`progress`, cancelable) sigue pendiente en §7.2.
3. **Test de igualdad capacidad→imagen: contra el venv del vendor, no el de EMVy.** Importar
   `modules.core.requirements` arrastra `modules.firmware.releases`, que hace `import certifi`
   (dep presente solo en el venv del vendor). El test usa `bt._venv_python(root)` y se salta si
   el venv del vendor no está listo (patrón de `test_run_capture_help`). El plan decía "por
   subprocess" — se concreta que **debe** ser el intérprete del vendor.
4. **Gating implementado como mecanismo, sin sub-tabs gated todavía.** El alcance de Sesión 1
   no añade Tags/Readers/…; `register_gated` queda listo para que Sesión 2+ solo llame a él.

**Pendiente para la siguiente sesión (Sesión 2 — Tags + Readers):** añadir los sub-tabs
**Tags** y **Readers** (helpers `bt.tags_read`/`readers_read` ya existen), registrarlos con
`firmware_panel.register_gated("tags"|"readers", widget)`, y los métodos `MainWindow.tags_read`/
`readers_read` que pinten el JSON en `CopyableDataTable`.

### Sesión 2 — DetectTags + DetectReaders — ✅ COMPLETA (2026-09-17)

**GUI — panel** (`emvy/gui/panels/firmware.py`):
- Dos sub-tabs nuevos en `self._sub`, ambos **gated** (`register_gated("tags"|"readers", …)`
  en `__init__`, así arrancan deshabilitados hasta que `status_json().caps` traiga la capacidad):
  - **Tags** (`_build_tags_tab`): `QSpinBox` de timeout (1–120 s, def. 15) + botón "Leer tag"
    → `win.tags_read(timeout)`; tabla Campo/Valor (`_tags_table`).
  - **Readers** (`_build_readers_tab`): timeout + botón "Detectar lector" → `win.readers_read`;
    tabla Campo/Valor (`_readers_table`).
- **Renderizadores** `show_tag(data)`/`show_reader(data)` + helpers `_kv_table()` (tabla
  Campo/Valor genérica) y `_fill_kv(table, dict)`. `tags read --json`/`readers read --json`
  devuelven **un objeto** con claves variables (uid/tech/protocol/atqa/sak/model para tags;
  ts_ms/tech/protocol/apdu/aid/label/n para readers), así que se pinta clave→valor genérico en
  vez de columnas fijas. Toleran lista (toman el primer objeto) y `None`→"—".

**GUI — MainWindow** (`emvy/gui/app.py`): `tags_read(timeout)`/`readers_read(timeout)` por
`submit(...)` sobre `bt.tags_read`/`bt.readers_read` (ya existían), con `on_result`
→`_on_tags_read`/`_on_readers_read` (pintan tabla + log) y `on_error`→`notify`.

**Tests** (`tests/test_gui.py`):
- `test_firmware_subtabs_and_status_gating`: actualizado — la lista de sub-tabs ahora es
  `[Dispositivo, Flashear, Tags, Readers]` y Tags arranca deshabilitado (gated).
- `test_firmware_tags_readers_render` (nuevo): `set_status` habilita ambos sub-tabs; `show_tag`
  pinta 4 filas con `None`→"—"; `show_reader` acepta una lista y toma el primer objeto.
- Suite completa con PySide6 instalado: **210 passed, 11 skipped**.

**Desviaciones y hallazgos respecto al plan:**
1. **`CopyableDataTable` es de la TUI, no de la GUI.** El plan (§5.2/§7 Sesión 2) decía pintar
   en `CopyableDataTable`, pero eso es un widget Textual. En la GUI se usa `QTableWidget` con
   selección de filas y sin edición (mismo patrón que `panels/readers.py`), que ya es
   copiable-por-selección.
2. **Tabla Campo/Valor en vez de columnas fijas.** Como `tags`/`readers` devuelven un único
   objeto con esquema distinto entre sí y ampliable por versión del vendor (p.ej. `model` en
   v1.3.0), una tabla clave→valor genérica es más robusta que columnas hardcodeadas y evita
   perder campos nuevos.
3. **PySide6 no estaba en el venv de dev** → `tests/test_gui.py` se saltaba entero
   (`importorskip`). Instalado (`uv pip install PySide6`) para verificar de verdad; con él la
   suite GUI corre (23 tests) y el total sube a 210 passed (antes 187 con GUI saltada).

**Pendiente para la siguiente sesión (Sesión 3 — magspoof):** helpers de orquestador
`magspoof_show/play/card_list/card_add/card_select/nfc_visa` (verificar `--json` por `--help`
antes) + sub-tab **Magspoof** (gated:magspoof) reutilizando editores Track1/Track2 del panel
Fuzzing; tests con `fakeserial`.

### Sesión 3 — magspoof — ✅ COMPLETA (2026-09-17)

**Superficie CLI verificada** (`vendor/bombercat-tools/modules/magspoof/cli.py` +
`docs/commands/magspoof.md`, v1.3.0): `show` y `card list` ofrecen `--json`; `play`,
`card add <name> --t1 --t2`, `card select <name>` y `nfc visa` **solo** confirman en texto (sin
`--json`). Ninguno acepta `-t`/timeout como flag (el `timeout` de los helpers es del subproceso).

**Orquestador** (`emvy/integrations/bombercat_tools.py`) — nueva sección magspoof:
- `_port_args(port)` — helper `["-p", port]` reutilizado por los seis wrappers.
- `magspoof_show(port, timeout) -> dict` — `show --json` → `{t1,t2,btn,analysis:{...}}`.
- `magspoof_play(port, timeout)` / `magspoof_nfc_visa(port, timeout)` → `CompletedProcess`.
- `magspoof_card_list(port, timeout) -> list[dict]` — **NO** usa `run_json`: `card list --json`
  emite JSONL (un objeto por tarjeta) y un store vacío es válido (lista vacía, no error), así que
  hace `run_capture` + `_extract_json` y filtra a dicts.
- `magspoof_card_add(name, *, t1, t2, port, timeout)` — omite `--t1`/`--t2` vacíos.
- `magspoof_card_select(name, *, port, timeout)`.

**GUI — panel** (`emvy/gui/panels/firmware.py`): sub-tab **Magspoof** (gated:magspoof,
`register_gated` en `__init__`). Dos `QGroupBox`: *Tarjeta activa* (botones Mostrar/Reproducir/
Emular Visa NFC + tabla Campo/Valor `_magspoof_table`) y *Tarjetas guardadas* (Listar + combo
`_card_name` + Seleccionar; `_cards_table` Tarjeta/Datos; formulario Nombre/T1/T2 + Agregar).
Renderizadores `show_magspoof(data)` (aplana `analysis.*` en la tabla) y `show_cards(cards)`
(una fila por tarjeta + puebla el combo de nombres).

**GUI — MainWindow** (`emvy/gui/app.py`): `magspoof_show/play/nfc_visa/card_list/card_add/
card_select` por `submit(...)` (puerto vía `firmware_panel.port()`); `card_add` valida
nombre + al menos un track y refresca el store al terminar; los de acción vuelcan con `log_result`.

**Tests** (`tests/test_bombercat_tools.py`, `tests/test_gui.py`):
- Orquestador (monkeypatch `run_capture`/`run_json`, sin hardware): `card list` JSONL→lista,
  store vacío→`[]`, construcción de args de `card add` (con/sin tracks vacíos), `show`→dict.
- GUI: lista de sub-tabs incluye "Magspoof"; `test_firmware_magspoof_render` (gating +
  `show_magspoof` aplana `analysis` + `None`→"—" + `show_cards` puebla tabla y combo).
- Suite completa: **216 passed, 11 skipped**.

**Desviaciones y hallazgos respecto al plan:**
1. **`fakeserial` no aplica.** El plan (§7 Sesión 3) proponía tests con `fakeserial`, pero eso
   emula el firmware EMVy para `emvy/readers/bombercat.py`; magspoof va por el **CLI del vendor**
   (subprocess). Los tests monkeypatchean `run_capture`/`run_json` (offline), igual que el patrón
   de Sesión 1/2 para la lógica propia del orquestador.
2. **Editores Track1/Track2 del panel Fuzzing NO reutilizados.** El plan lo sugería "donde
   aplique"; dos `QLineEdit` autocontenidos para T1/T2 en el formulario *card add* son más simples
   y evitan acoplar los paneles. La validación de formato de track la hace el propio CLI del vendor.
3. **`card list` no puede ir por `run_json`.** `run_json` trata "sin JSON" como error, pero un
   store vacío (0 tarjetas → 0 líneas JSON) es un estado legítimo → helper dedicado con
   `_extract_json`.

**Pendiente para la siguiente sesión (Sesión 4 — Mifare):** helpers `mifare_keys/check/dump/
restore` + sub-tab **Mifare** (gated:mifare) con flujo de archivos intermedios en
`<proy>/artifacts/`; `dump` produce un JSON de tarjeta integrable como captura del proyecto.

### Refactor ADR-001 — Un Tab de nivel superior por firmware — ✅ COMPLETO (2026-09-17)

Ejecuta la decisión **ADR-001** (supersede §5.1): el panel único "BomberCat" con `QTabWidget`
interno se abre en **un panel/Tab de nivel superior por firmware** dentro del grupo `HARDWARE`
de la barra lateral. Refactor mecánico (se mueve la lógica, no se reescribe).

**GUI — paneles** (`emvy/gui/panels/firmware.py`, reescrito):
- `BaseFirmwarePanel(QWidget)` — base común: `capability` (la que habilita el panel; `None` =
  control-plane), `set_status(st)` que se **auto-gatea** (`setEnabled(capability in caps)`),
  `port()` (delega en `MainWindow.firmware_port()`), `log`/`log_result`, y helpers de UI
  (`_kv_table`/`_fill_kv`/`_hint`/`_gate_hint`). Reemplaza `register_gated`/`_apply_gating`.
- `DevicePanel(BaseFirmwarePanel)` (`capability=None`, siempre activo) — **absorbe** los antiguos
  sub-tabs *Dispositivo* + *Flashear* como dos `QGroupBox` apilados; **posee el `QLineEdit` del
  puerto serie único** (`_port`). Es el único que flashea y refresca `status`.
- `TagsPanel`/`ReadersPanel`/`MagspoofPanel` — un panel por firmware, `capability="tags"/
  "readers"/"magspoof"`, `needs_image` para la pista de gating. La lógica de render
  (`show_tag`/`show_reader`/`show_magspoof`/`show_cards`) viaja tal cual con su panel.

**GUI — MainWindow** (`emvy/gui/app.py`):
- `self.firmware_panel` → cuatro paneles `fw_device`/`fw_tags`/`fw_readers`/`fw_magspoof` +
  `self.firmware_panels` (lista para el broadcast). Import de `ReadersPanel` **aliaseado**
  a `FwReadersPanel` (colisión con el panel PC/SC `panels.readers.ReadersPanel`).
- `addTab` por panel; `_NAV_GROUPS` grupo `HARDWARE` = *Dispositivo/Tags/Readers/Magspoof*;
  `_CONSOLE_TABS` los incluye a los cuatro. El mapeo `_nav_to_tab` (por etiqueta) funciona solo.
- `firmware_port()` (nuevo) — fuente única del puerto (lee `fw_device.port()`).
- `_on_device_status` hace **broadcast** de `set_status(st)` a `firmware_panels` → todos
  re-gatean a la vez desde el mismo status. El resto de métodos (`refresh_device`, `flash_image`,
  `tags_read`, `magspoof_*`…) direccionan el panel concreto (`fw_device`/`fw_tags`/…).

**Tests** (`tests/test_gui.py`): `test_all_eleven_tabs`→`test_top_level_tabs` (14 tabs, HARDWARE
abierto por firmware); `test_firmware_subtabs_and_status_gating` reemplazado por
`test_firmware_device_status_and_gating_broadcast` (gating **por panel** vía el broadcast de
`MainWindow`) + `test_firmware_port_is_shared` (puerto único). Tags/Readers/Magspoof render se
prueban sobre su nuevo panel. Suite: **217 passed, 11 skipped**.

**CLAUDE.md** §5: descripción del panel `firmware` actualizada (Tabs por firmware + broadcast).

**Desviaciones respecto a la Recomendación de refactor de ADR-001:**
1. **Un solo archivo `firmware.py`, varias clases** (no un archivo por firmware). La propia ADR
   admite "un archivo **o** clase por firmware"; mantener un archivo preserva el historial de git
   y es más lean ahora. Si crece (Mifare/Relay), extraer a un paquete `firmware/` es trivial.
2. **Gating a nivel de panel completo** (`self.setEnabled(...)`), no de ítem de barra lateral: el
   ítem sigue navegable pero el contenido del panel gated aparece deshabilitado, con una pista
   (`_gate_hint`) que remite a *Dispositivo → Flashear*. La CTA "Flashear <imagen> para habilitar"
   dentro del propio panel gated (§6) queda como pulido posterior; el camino de flasheo dirigido
   ya existe en `DevicePanel`.
3. **Sin `BaseFirmwarePanel` como controlador inyectado**: herencia simple (la ADR ofrecía ambas).

### Sesión 4 — Mifare (MifareClassic) — ✅ COMPLETA (2026-09-17)

Implementada **como panel propio** (ADR-001), no como sub-tab. La placa expone `mifare`
solo con la imagen `MifareClassic`; el panel arranca gated y se habilita por el broadcast
de `set_status`.

**Superficie CLI verificada** (`vendor/bombercat-tools/modules/tags/mifare/`, v1.3.0):
- `keys --json` → JSONL (`{"name","key"}` por línea, como `magspoof card list`).
- `check` produce ficheros: `--output-keys FILE` (el `sector:keyA:keyB` que consume `dump`),
  `--sectors N` (16=1K, 40=4K), `--keys FILE` (diccionarios extra, repetible), `--force`.
  **Ojo:** `dump` necesita el fichero de `--output-keys`, **no** el de `-o/--out` (keyfile
  plano) — por eso el helper escribe `--output-keys`.
- `dump --keys-file FILE --out FILE --json` (vuelca la tarjeta a JSON canónico y lo emite
  también en stdout). `restore --dump FILE` (reescribe la tarjeta).
- Todos usan `@device_options` → aceptan `-p/--port` (como magspoof).

**Orquestador** (`emvy/integrations/bombercat_tools.py`) — nueva sección Mifare:
- `mifare_keys(port, timeout) -> list[dict]` — `run_capture` + `_extract_json` (JSONL, no
  `run_json`).
- `mifare_check(sector_keys_out, *, sectors=16, keys=None, force=True, port, timeout)` →
  `CompletedProcess`.
- `mifare_dump(keys_file, out_json, *, sectors=16, force=True, port, timeout) -> dict`
  (escribe el fichero **y** devuelve el dict del volcado vía `--json`).
- `mifare_restore(dump_json, *, sectors=None, write_block0=False, skip_trailers=False,
  port, timeout)` → siempre pasa **`--yes`** (el subproceso no tiene TTY; sin `--yes`,
  `restore` se colgaría en la confirmación interactiva del bloque 0).

**Modelo de proyecto** (`emvy/project/model.py`): nueva propiedad `Project.artifacts_dir`
(`<proyecto>/artifacts/`), donde viven el keyfile y el dump JSON.

**GUI — panel** (`emvy/gui/panels/firmware.py`): `MifarePanel(BaseFirmwarePanel)`,
`capability="mifare"`, `needs_image="MifareClassic"`. Grupo *Recuperar claves y volcar*
(SpinBox de sectores + «Ver claves por defecto» → `_keys_table`; «Recuperar y volcar» →
`win.mifare_dump(sectores)` → `_dump_table` con uid+nº de sectores) y grupo *Restaurar*
(combo de dumps de artifacts/ + «Restaurar a la tarjeta»). Renderizadores `show_keys`,
`show_dump`, `set_dumps`.

**GUI — MainWindow** (`emvy/gui/app.py`): `mifare_keys()`, `mifare_dump(sectors)` (encadena
`check`+`dump` en **un solo worker** y guarda en artifacts/ del proyecto activo),
`mifare_reload_dumps()` (puebla el combo con `mifare-*.json`), `mifare_restore(name)`.
Panel `fw_mifare` añadido a `firmware_panels` (recibe el broadcast), Tab **Mifare** +
ítem de barra lateral (`HARDWARE`, icono `square`) + `_CONSOLE_TABS`. `import time` añadido
(sello de tiempo del nombre de fichero).

**Tests**:
- Orquestador (`tests/test_bombercat_tools.py`): `keys` JSONL→lista, args de `check`
  (con dict extra + `--force` + puerto), args de `dump` + dict de retorno, y que `restore`
  **siempre** lleva `--yes`.
- GUI (`tests/test_gui.py`): `test_top_level_tabs` incluye "Mifare";
  `test_firmware_mifare_render` (gating + `show_keys` + `show_dump` resume uid/sectores);
  `test_firmware_mifare_dumps_combo` (`mifare_reload_dumps` filtra `mifare-*.json` del
  proyecto activo). Suite: **223 passed, 11 skipped**.

**Desviaciones y hallazgos respecto al plan:**
1. **`check -o` ≠ lo que `dump` necesita.** El plan (§4.2) proponía `mifare_check(out_keyfile)`
   → `check -o` (keyfile plano). Pero `dump --keys-file` consume el fichero
   `sector:keyA:keyB` de **`--output-keys`**. El helper escribe `--output-keys`; el keyfile
   plano no se usa en este flujo.
2. **`restore` necesita `--yes` sí o sí.** Sin TTY en el subproceso, la confirmación
   interactiva del bloque 0 colgaría el worker. Se pasa siempre (no reescribimos bloque 0
   por defecto, pero es una salvaguarda barata).
3. **El dump NO es un CardDump EMV** → no se integra con `store.import_capture` (esquema
   distinto: uid+sectores vs `{atr,applications,blobs}`). Se guarda como **artefacto** del
   proyecto (`artifacts/`), no como captura del Explorador. El plan lo dejaba como "si aplica".
4. **`check`+`dump` en un solo worker.** En vez de dos `submit` encadenados por `on_result`,
   un closure `_run()` corre ambos subcomandos secuencialmente en el hilo de trabajo y
   devuelve el dict del dump — un solo viaje, errores unificados en `on_error`.
5. **Panel propio desde el principio** (no sub-tab que luego se refactoriza): ADR-001 ya
   estaba aplicado, así que Sesión 4 nace como `MifarePanel`.

### Sesión 5 — Relay NFCGate — ✅ COMPLETA (2026-09-18)

Última capacidad de la matriz del §3. Implementada como panel propio (ADR-001) desde el
principio, igual que Mifare.

**Superficie CLI verificada** (`vendor/bombercat-tools/modules/nfcgate/cli.py` +
`modules/capture/cli.py`, v1.3.0): **ningún** subcomando de `relay`/`capture` ofrece `--json`
(a diferencia de `tags`/`readers`/`magspoof show`/`mifare keys`). `config show` y `status`
imprimen tablas rich de 2 columnas con la misma forma que `bombercat status` (filas `│ clave │
valor │`, con continuación de celda). `config wifi`/`config nfcgate`/`run`/`stop` solo
confirman en texto. `run` es **bloqueante dentro del propio CLI del vendor**: acepta el
arranque y sondea su propio `status` hasta 'relaying'/'error' o agotar un presupuesto de
~45s (`_RUN_BRINGUP_TIMEOUT` en el CLI) — no hace falta que EMVy implemente ese sondeo, solo
darle margen de timeout al subprocess. `monitor` y `capture start` son **streaming sin fin**
(hasta Ctrl-C o que el link caiga); ninguno de los dos encaja en el patrón `run_capture(timeout=…)`
usado por el resto de capacidades.

**Orquestador** (`emvy/integrations/bombercat_tools.py`) — nueva sección Relay NFCGate:
- `_table_rows(text) -> dict[str,str]` — se **extrae** de `parse_status` (que ahora lo llama)
  el parseo genérico de tablas rich de 2 columnas con continuación de celda; lo reutilizan
  `parse_relay_config` y `parse_relay_status`. Refactor puro, sin cambiar el comportamiento de
  `parse_status` (sus tests siguen verdes tal cual).
- `parse_relay_config(text) -> dict` / `relay_config_show(port, timeout)` — `{fw, role, ssid,
  server, port, session, state}`.
- `relay_config_wifi(ssid, password="", *, save=True, port, timeout)` /
  `relay_config_nfcgate(server, session, role, *, save=True, port, timeout)` — wrappers finos
  (`--save`/`--no-save`, `role` es `"reader"`/`"card"`).
- `parse_relay_status(text) -> dict` / `relay_status(port, timeout)` — `{state,
  link_connected: bool, peer_present: bool, relayed}`. La tabla de `relay status` usa la
  etiqueta **`"APDU pairs relayed"`** (con mayúsculas, a diferencia del resto de claves en
  minúscula) — `parse_relay_status` la busca tal cual.
- `relay_run(port, timeout=55)` / `relay_stop(port, timeout)` — pasan directo; el timeout por
  defecto de `run` (55s) da margen al presupuesto interno del CLI (~45s) más margen de proceso.
- `capture_stop(port, timeout)` — desarma el tap (`capture stop`), idempotente.
- `capture_run(output, *, duration=30, force=True, strict=False, port) -> (CompletedProcess,
  timed_out: bool)` — **la pieza nueva del plan**: acota `capture start -o FILE` (que por sí
  solo no termina nunca) con el propio `timeout` de `subprocess.run`. Al vencer, `TimeoutExpired`
  trae en `.stdout`/`.stderr` lo que el proceso alcanzó a escribir antes del `kill()` (`subprocess.
  run` los recolecta en su manejador antes de re-lanzar); como un `kill()` duro salta el `finally`
  del comando del vendor (que desarma el tap con `capture off`), `capture_run` **siempre** llama a
  `capture_stop` después en un `finally` propio, gane o pierda la carrera contra la duración.

**GUI — panel** (`emvy/gui/panels/firmware.py`): `RelayPanel(BaseFirmwarePanel)`,
`capability="relay"`, `needs_image="NFCGate"`. Tres grupos: *Configuración* (WiFi: SSID +
contraseña (echo password) + «Guardar» + botón; NFCGate: servidor + sesión (1-255) + rol
(reader/card) + «Guardar» + botón; «Ver configuración» → tabla `_config_table`), *Relay*
(Iniciar/Detener/Actualizar estado → tabla `_status_table`) y *Capturar APDUs relayados* (spinbox
de duración 5-600s + «Capturar a artifacts/»). Renderizadores `show_config`/`show_status` (kv
genéricos). Icono de sidebar: `"shield"` (reutilizado de Intercept — grupos de barra distintos,
sin conflicto visual).

**GUI — MainWindow** (`emvy/gui/app.py`): `self.fw_relay` añadido a `firmware_panels` (recibe el
broadcast), Tab **Relay** + ítem de sidebar (`HARDWARE`) + `_CONSOLE_TABS`. Métodos
`relay_config_wifi/nfcgate`, `relay_config_show`, `relay_run`/`relay_stop` (ambos refrescan
`relay_status()` al terminar vía `_on_relay_run`/`_on_relay_stop`), `relay_status`,
`relay_capture(duration)` — genera `<proyecto>/artifacts/relay-<timestamp>.pcap` (mismo patrón de
sellado que `mifare_dump`), requiere proyecto activo, y `_on_relay_capture` registra en el log si
la captura terminó por duración agotada o porque el link cayó solo.

**Tests**:
- Orquestador (`tests/test_bombercat_tools.py`): `parse_relay_config`/`parse_relay_status`
  (tabla completa, incluida la clave `"APDU pairs relayed"` con mayúsculas), construcción de
  args de `config wifi`/`config nfcgate` (con/sin `--save`), `relay_run`/`relay_stop` pasan
  igual que el resto, y dos tests de `capture_run`: complección normal dentro del plazo (con
  `capture stop` posterior igualmente) y **timeout** (verifica que el `stdout` parcial de
  `TimeoutExpired` llega al `CompletedProcess` devuelto y que `capture stop` se llama SIEMPRE,
  con el mismo puerto).
- GUI (`tests/test_gui.py`): `test_top_level_tabs` incluye "Relay";
  `test_firmware_device_status_and_gating_broadcast` cubre que `fw_relay` arranca deshabilitado
  y no se habilita con capacidades ajenas; `test_firmware_relay_render` (gating + `show_config`
  + `show_status`). Se **omitió** un test de integración `win.relay_capture()` de extremo a
  extremo contra el `QThreadPool` real: el propio docstring de `tests/test_gui.py` ya fija la
  convención — las operaciones de hardware/worker se prueban a nivel de orquestador o de
  renderizador de panel, no disparando el pool real desde una prueba de GUI (los dos únicos
  tests que sí ejercitan el pool, `test_worker_delivers_result/error`, prueban el mecanismo
  genérico de `worker.py`, no un método de `MainWindow`).
- Suite completa: **233 passed, 11 skipped** (antes 223; +10 tests: 8 de orquestador + 2 de GUI).

**Desviaciones y hallazgos respecto al plan:**
1. **`capture_start` del plan (§4.2) se implementó como `capture_run`, acotado por duración.**
   El plan proponía una firma `capture_start(*, wireshark=False, on_line=None)` pensada para
   streaming real (como §7.2 prevé para `watch`/`monitor`/`flash`/`scan`). Pero `capture start`
   del vendor no tiene ninguna noción de duración — corre hasta Ctrl-C o que el link caiga — y
   el streaming genérico con cancelación (`want_progress` + kill por botón "Detener") queda
   fuera del alcance de esta sesión (§7.2 es "transversal", sesión aparte). La solución pragmática
   —consistente con cómo Sesión 1 ya resolvió `flash` sin streaming (ver desviación 2 de Sesión
   1)— es acotar con el timeout del propio `subprocess.run` y renunciar a Wireshark en vivo
   (`-ws`) desde la GUI, que si necesita una tubería con lector en el otro extremo.
2. **`capture_run` SIEMPRE llama a `capture_stop` en un `finally`, no solo en el camino feliz.**
   Necesario porque un `kill()` duro (lo que dispara `TimeoutExpired`) no le da al comando del
   vendor la oportunidad de correr su propio `finally` (que desarma el tap con `capture off`);
   sin este paso extra, un board capturado por la GUI quedaría con el tap armado indefinidamente.
3. **`_table_rows` extraído como refactor incidental.** `parse_status` ya tenía exactamente la
   lógica que `parse_relay_config`/`parse_relay_status` necesitaban (tabla rich de 2 columnas
   con continuación de celda); en vez de triplicar el parser, se factorizó sin tocar el
   comportamiento observable de `parse_status` (mismos tests, sin cambios, siguen en verde).
4. **La etiqueta `"APDU pairs relayed"` rompe la convención de minúsculas del resto de tablas**
   (`relay status` la imprime tal cual, con mayúsculas, a diferencia de `state`/`link connected`/
   `peer present`). `parse_relay_status` la busca por su literal exacto — un cambio de
   capitalización en una versión futura del vendor la rompería silenciosamente (degradaría a
   `"relayed": "0"` por defecto, no un error dado); vigilar si se sube de v1.3.0.
5. **Sin panel de "Wireshark en vivo" ni de `relay monitor`.** Ambos son streaming sin fin con
   semántica de "Ctrl-C para salir" que no tiene un equivalente limpio de un solo disparo; quedan
   explícitamente fuera (el plan ya los marcaba como "extra opcional"/pendiente de §7.2).

**Pendiente para futuras sesiones:** §7.1 (paridad TUI, no bloqueante) y §7.2 (streaming
genérico cancelable para `watch`/`monitor`/`flash`/`scan`/`capture`, transversal a todos los
paneles). No hay más capacidades de la matriz del §3 pendientes de cablear.
