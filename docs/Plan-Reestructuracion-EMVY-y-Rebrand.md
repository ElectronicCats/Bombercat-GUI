# Plan: reestructuración de Tabs EMVY + rebrand genérico

**Estado:** En curso — v1.0 (2026-09-18). **Objetivo 1 completado** (Sesiones O1-1, O1-2, O1-3;
§8); Objetivo 2 (rebrand) pendiente.
**Alcance:** dos objetivos independientes pero secuenciados:
1. **Objetivo 1** — aplicar la reestructuración de Tabs de ADR-001 a la superficie EMVY:
   disolver los sub-tabs restantes y regruparlos como Tabs de nivel superior.
2. **Objetivo 2** — **rebrand completo** del producto/paquete, sustituyendo la nomenclatura
   "EMVY"/"EMVyController" por nombres **descriptivos por función**, con `git mv` que preserva
   el histórico.
**Audiencia:** desarrolladores que ejecutarán este plan en sesiones posteriores.
**Referencia de patrón:** `docs/Plan-Integracion-Firmwares-BomberCat.md`, en concreto **ADR-001**
("un Tab de nivel superior por firmware") y su Progress log — ya ejecutado para los firmwares
oficiales; este plan lo extiende a EMVY y renombra lo que quedó con marca EMVY.

> Written for: desarrolladores del repo. Asume familiaridad con `emvy/gui/` (PySide6),
> `emvy/config.py` (rutas XDG), `pyproject.toml`, y con ADR-001 del plan de firmwares.

---

## 0. TL;DR

- **Hoy no existe un Tab literalmente llamado "EMVY".** La funcionalidad EMVY está repartida en
  **6 Tabs de nivel superior** — `Explorador`, `Herramientas`, `Cobros`, `PoC`, `Intercept`,
  `Fuzzing` — de los cuales **solo `Herramientas` y `Fuzzing` mantienen `QTabWidget` interno con
  sub-tabs**; los otros cuatro ya son Tabs planos. (Confirmado con el usuario: estos 6 son "los
  derivados de EMVY".)
- **Objetivo 1** = terminar de aplicar ADR-001 a esta superficie: **disolver los sub-tabs** de
  `Herramientas` (Flags/ISO 8583/Escritura) y `Fuzzing` (Editor de tarjeta/Emulación NFC-EMV/
  Registro EMV/Banda magnética) en **Tabs de nivel superior**, y **regruparlos** en la barra
  lateral con la misma lógica de `_NAV_GROUPS`. Trabajo mayoritariamente **mecánico** (mover
  paneles, no reescribir lógica).
- **Objetivo 2** = **rebrand completo**. El producto se llama uniformemente "EMVy Controller" /
  paquete `emvy` / CLI `emvyctl` / `emvycontroller` (pyproject) / rutas XDG `~/.local/share/emvy`.
  No hay marca alterna en el repo. Se sustituye por un nombre **descriptivo por función**
  (**decisión D-0**, §2). Blast radius grande: **183 líneas de import** en ~37 archivos, **5
  variables de entorno `EMVY_*`**, rutas de datos del usuario, y todo `packaging/`.
- **Orden recomendado:** **Objetivo 1 primero** (deja el conjunto final de archivos de panel),
  **Objetivo 2 después** (pasada de renombrado sobre ese conjunto). Ver §10.

---

## 1. Estado actual (hallazgos de investigación, con citas)

### 1.1 Mapa de Tabs (`emvy/gui/app.py`)

`MainWindow` monta **16 páginas** en un `QTabWidget` con la barra de pestañas oculta
(`self.tabs.tabBar().hide()`, `app.py:153`); la navegación real es el `QListWidget#nav` agrupado
por `_NAV_GROUPS` (`app.py:201-233`). El mapeo fila→página lo hace `_nav_to_tab`, que **une por
etiqueta de texto** (`app.py:243-256`), así que **añadir/quitar/regrupar Tabs no requiere tocar
`_nav_to_tab`**: basta con que la etiqueta de `addTab` coincida con la de `_NAV_GROUPS`.

| # tab | Etiqueta | Instancia | Clase / archivo | ¿EMVY? |
|---|---|---|---|---|
| 0 | Inicio | `dashboard_panel` | `DashboardPanel` · `panels/dashboard.py` | no (sesión) |
| 1 | Proyectos | `projects_panel` | `ProjectsPanel` · `panels/projects.py` | no |
| 2 | Variables | `variables_panel` | `VariablesPanel` · `panels/variables.py` | no |
| 3 | Lectores | `readers_panel` | `ReadersPanel` · `panels/readers.py` | no |
| 4 | **Explorador** | `explorer_panel` | `ExplorerPanel` · `panels/explorer.py` | **sí** (Tab plano) |
| 5 | **Herramientas** | `tools_panel` | `ToolsPanel(QTabWidget)` · `panels/tools.py` | **sí** (3 sub-tabs) |
| 6 | **Cobros** | `charges_panel` | `ChargesPanel` · `panels/charges.py` | **sí** (Tab plano) |
| 7 | **PoC** | `poc_panel` | `PocPanel` · `panels/poc.py` | **sí** (Tab plano) |
| 8 | **Intercept** | `intercept_panel` | `InterceptPanel` · `panels/intercept.py` | **sí** (Tab plano) |
| 9 | Dispositivo | `fw_device` | `DevicePanel` · `panels/firmware.py` | no (HW, ADR-001) |
| 10 | Tags | `fw_tags` | `TagsPanel` · `panels/firmware.py` | no (HW) |
| 11 | Readers | `fw_readers` | `ReadersPanel` (alias `FwReadersPanel`) · `panels/firmware.py` | no (HW) |
| 12 | Magspoof | `fw_magspoof` | `MagspoofPanel` · `panels/firmware.py` | no (HW) |
| 13 | Mifare | `fw_mifare` | `MifarePanel` · `panels/firmware.py` | no (HW) |
| 14 | Relay | `fw_relay` | `RelayPanel` · `panels/firmware.py` | no (HW) |
| 15 | **Fuzzing** | `fuzz_panel` | `FuzzPanel` · `panels/fuzz.py` | **sí** (4 sub-tabs) |

`addTab` en `app.py:134-149`; instancias en `app.py:106-132`.

### 1.2 Sub-tabs a disolver

**`ToolsPanel(QTabWidget)`** (`panels/tools.py:43-52`) — 3 sub-tabs:
`Flags` (`_FlagsTool`), `ISO 8583` (`_IsoTool`), `Escritura` (`_WriteTool`).
Reexpone a `MainWindow`: `log_write()` / `iso_response()` (`tools.py:55-60`).

**`FuzzPanel`** (`panels/fuzz.py`) — un `QWidget` con un `QTabWidget` interno `sub` (`fuzz.py:50`),
4 sub-tabs (orden real de `addTab`, `fuzz.py:51-54`):
1. `Editor de tarjeta` → `_card_editor()` (`fuzz.py:385`): cargar tarjeta (lector / RAM BomberCat /
   captura), editar PAN/caducidad/servicio/AID/titular/Track2, emular la editada (`win.emit_emv`).
2. `Emulación NFC/EMV` → `_ndef_lane()` (`fuzz.py:162`): selector de Fuente que emula tag NDEF o
   tarjeta EMV vía BomberCat (`win.emit_ndef` / `win.emit_emv`).
3. `Registro EMV` → `_emv_lane()` (`fuzz.py:106`): generar/editar un registro EMV hex y escribirlo
   en tarjeta de prueba (`win.write_record`).
4. `Banda magnética` → `_track_lane()` (`fuzz.py:61`): generar/editar Track1/Track2 y disparar por
   BomberCat magspoof (`win.emit_magspoof`).

> **Nota:** el docstring de `fuzz.py:1-10` dice "tres carriles" pero el código tiene **4** (el editor
> se añadió después). No es fuente de verdad; el código sí.

### 1.3 Auditoría de nomenclatura "EMVY" (Objetivo 2)

| Elemento | Ubicación | Definición |
|---|---|---|
| Paquete Python | `emvy/` (raíz) | — |
| Shim CLI | `emvyctl.py` (raíz) | `from emvy.cli import main` (`emvyctl.py:5`) |
| Nombre de distribución | `pyproject.toml:2` | `name = "emvycontroller"` |
| Console-script | `pyproject.toml:27-28` | `emvyctl = "emvy.cli:main"` |
| `py-modules` / `packages.find` | `pyproject.toml:34-38` | `["emvyctl"]` / `include = ["emvy*"]` |
| `APP_NAME` (rutas XDG) | `emvy/config.py:13` | `= "emvy"` → `~/.local/share/emvy`, `~/.config/emvy` |
| Versión/release/marca | `emvy/__init__.py:1,26-27` | docstring "EMVyController", `__version__`, `__release__` |
| Título ventana / app Qt | `emvy/gui/app.py:74,1384` | `"EMVy Controller …"` / `setApplicationName("EMVy Controller")` |
| Spec PyInstaller | `packaging/EMVyController.spec` | ENTRY `emvy_gui.py`, icon `emvy.ico` (`spec:14,41`) |
| Entry GUI empaquetado | `packaging/emvy_gui.py` | `from emvy.gui.app import run_gui` |
| Icono | `packaging/emvy.svg` | usado por `Dockerfile.appimage:44-51` |
| AppImage / Docker tags | `build-appimage.sh:11-22`, `Dockerfile.appimage/windows` | `emvy-appimage`, `emvy-win`, `EMVy_Controller-*.AppImage` |
| Variables de entorno | `config.py`, `store.py`, `gui/app.py`, `tui/app.py` | `EMVY_ENGAGEMENTS`, `EMVY_BOMBERCAT_TOOLS`, `EMVY_PROJECT`, `EMVY_GUI_KEEP_QT_ENV`, `EMVY_THEME` |
| Firmware | `firmware/EMVyBomberCat/` | sketch unificado (`.ino` + `modes_*.ino` + `emv_emu.h` + `build/`) |
| Refs a firmware | `emvy/readers/bombercat.py` | 6 menciones en prosa: líneas 421, 442, 491, 519, 525, 574 |
| Docs / README | `README.md`, `CLAUDE.md` | banner y título |

**Tamaño del rebrand:** `grep -rnE '(from|import) +emvy' --include='*.py'` (excl. `.venv`) → **183
líneas** en ~37 archivos (código + `tests/`). Las 5 `EMVY_*` son **superficie de usuario** (env
vars) → requieren alias de compatibilidad.

**No existe marca alterna** en el repo: "EMVy Controller" es el único nombre. El rebrand parte de
cero, no reconcilia dos nombres.

---

## 2. Decisiones abiertas (resolver antes de ejecutar)

| ID | Decisión | Recomendación | Notas |
|---|---|---|---|
| **D-0** | Nombre del paquete / CLI / producto | Paquete `cardsec`, CLI `cardsec`, shim `cardsecctl.py`, distribución `cardsec`, producto "Card Security Suite", prefijo env `CARDSEC_` | "Descriptivo por función" (card security). Todo el plan usa el token **`⟨PKG⟩ = cardsec`**; para cambiarlo, ajústese aquí y en un único find/replace. Alternativas: `cardlab`, `paycardtest`. |
| **D-1** | Solapamiento "Banda magnética" (Fuzzing) ↔ panel `Magspoof` (HW) | Mantener el carril de **fuzzing de banda** (plantillas mutadas, `core.cardfuzz`) como Tab propio distinto del panel Magspoof (operación del store); documentar que ambos usan magspoof | Alternativa: plegar las plantillas dentro de `MagspoofPanel` como sección secundaria. Es una decisión de UX, no bloquea. |
| **D-2** | Migración de datos XDG al cambiar `APP_NAME` | Añadir `config._migrate_legacy_data()`: si el dir nuevo no existe y `~/.local/share/emvy` sí, **renombrar** (o copiar) una vez; leer también env vars viejas | Sin esto, los proyectos/capturas del usuario quedan huérfanos. Obligatorio. §5.4. |
| **D-3** | Agrupación de la barra lateral tras disolver sub-tabs | Ver estructura propuesta en §4.1 (grupos `ANÁLISIS` / `EMULACIÓN` / `OPERACIONES`) | Ajustable; el enrutamiento por etiqueta lo soporta sin cambios de código. |
| **D-4** | Firmware `EMVyBomberCat` → nombre por función | `firmware/bombercat_multitool/` (la "navaja suiza" de §12 de CLAUDE.md) | Arduino exige que el `.ino` tenga el **mismo basename** que la carpeta → renombrar ambos. §6.1. |

> El resto del plan asume las recomendaciones. Donde se lee `⟨PKG⟩`, sustitúyase por el valor D-0.

---

## ADR-002 — EMVY como superficie plana de Tabs (extiende ADR-001)

**Estado:** Propuesta (2026-09-18). **Extiende:** ADR-001 del plan de firmwares
(un Tab de nivel superior por firmware). **Afecta:** `emvy/gui/app.py` (`_NAV_GROUPS`, `addTab`,
`_CONSOLE_TABS`), `emvy/gui/panels/tools.py`, `emvy/gui/panels/fuzz.py`, `tests/test_gui.py`.

### Contexto
ADR-001 estableció que **cada firmware/capacidad es un Tab de nivel superior** (no sub-tabs dentro
de un panel genérico), conducido por la barra lateral agrupada. Se aplicó al grupo `HARDWARE`
(Dispositivo/Tags/Readers/Magspoof/Mifare/Relay). La superficie **EMVY** (6 Tabs de §1.1) quedó
fuera de ese refactor: dos de sus Tabs (`Herramientas`, `Fuzzing`) **aún anidan** `QTabWidget`
interno — exactamente el antipatrón que ADR-001 eliminó en HARDWARE.

### Decisión
Aplicar el **mismo principio** a la superficie EMVY: **ningún Tab de nivel superior contiene
sub-tabs**. Cada función EMVY es un Tab plano, gobernado por `_NAV_GROUPS`. En concreto:
- `Herramientas` se **disuelve** → `Flags`, `ISO 8583`, `Escritura` como Tabs de nivel superior.
- `Fuzzing` se **disuelve** → `Editor de tarjeta`, `Emulación`, `Registro EMV`, `Banda (fuzz)` como
  Tabs de nivel superior.
- `Explorador`, `Cobros`, `PoC`, `Intercept` ya son planos → solo se **regrupan** en la barra
  lateral (sin cambios de código de panel).

### Justificación
1. **Consistencia con ADR-001.** El mismo argumento de descubribilidad y de no-anidar aplica igual:
   una función enterrada a dos niveles (sidebar → Herramientas → Flags) sube a un nivel.
2. **La barra lateral ya agrupa sin límite práctico** (`_NAV_GROUPS`): absorbe los Tabs planos
   nuevos sin desbordar (mismo motivo por el que HARDWARE se abrió por firmware).
3. **El enrutamiento no cambia**: `_nav_to_tab` une por etiqueta (`app.py:243-256`); mover un panel
   de sub-tab a Tab de primer nivel es añadir un `addTab(label)` + una entrada en `_NAV_GROUPS`.

### Consecuencias
- **Positivas:** navegación plana y homogénea con HARDWARE; cada función EMVY evoluciona en su
  panel; los renderizadores (`_FlagsTool`, `_IsoTool`, `_WriteTool`, y los carriles de `FuzzPanel`)
  se **mueven tal cual**, no se reescriben.
- **Coste:** `ToolsPanel`/`FuzzPanel` dejan de ser contenedores `QTabWidget`; sus reexpones a
  `MainWindow` (`log_write`, `iso_response`, `emit_*`, `write_record`) se recablean al panel
  concreto. Actualizar `tests/test_gui.py` (asserts de sub-tabs → asserts de Tabs de primer nivel).

---

## 3. Objetivo 1 — reestructuración de Tabs (detalle)

### 3.1 Estructura de Tabs objetivo (propuesta, D-3)

**Antes** (barra lateral, grupos EMVY subrayados):

```
SESIÓN     · Inicio · Proyectos · Variables · Lectores
TARJETA    · Explorador · Herramientas[Flags|ISO 8583|Escritura]
OPERACIONES· Cobros · PoC · Intercept · Fuzzing[Editor|Emulación|Registro|Banda]
HARDWARE   · Dispositivo · Tags · Readers · Magspoof · Mifare · Relay
```

**Después:**

```
SESIÓN     · Inicio · Proyectos · Variables · Lectores
ANÁLISIS   · Explorador · Flags · ISO 8583
EMULACIÓN  · Editor de tarjeta · Emulación · Registro EMV · Escritura · Banda (fuzz)
OPERACIONES· Cobros · PoC · Intercept
HARDWARE   · Dispositivo · Tags · Readers · Magspoof · Mifare · Relay
```

- `Flags`, `ISO 8583`, `Escritura` salen de `Herramientas`. `Escritura` se agrupa con las de
  edición/emulación (escribe en tarjeta); `Flags`/`ISO 8583` con las de análisis.
- `Editor de tarjeta`, `Emulación`, `Registro EMV`, `Banda (fuzz)` salen de `Fuzzing`.
- `Explorador`/`Cobros`/`PoC`/`Intercept` no cambian de código, solo de grupo.
- (Ajustable — la unión por etiqueta permite recolocar sin tocar `_nav_to_tab`.)

### 3.2 Archivos que cambian

| Archivo | Cambio |
|---|---|
| `emvy/gui/panels/tools.py` | Separar `_FlagsTool`/`_IsoTool`/`_WriteTool` en **3 paneles `QWidget` de primer nivel**. Eliminar `ToolsPanel(QTabWidget)`. Cada clase conserva su lógica; se exponen como `FlagsPanel`/`IsoPanel`/`WritePanel`. |
| `emvy/gui/panels/fuzz.py` | Separar los 4 carriles en **4 paneles de primer nivel** (`_card_editor`→`CardEditorPanel`, `_ndef_lane`→`EmulationPanel`, `_emv_lane`→`EmvRecordPanel`, `_track_lane`→`MagfuzzPanel`). Extraer el estado compartido (si lo hay: fuente de tarjeta, botones Detener/Reboot comunes) a `MainWindow` o a un mixin, como hizo `BaseFirmwarePanel`. |
| `emvy/gui/app.py` | Imports de los nuevos paneles; instanciar; `addTab` por panel; `_NAV_GROUPS` regrupado (§3.1); `_CONSOLE_TABS` con las nuevas etiquetas que emitan tráfico serie (`Emulación`, `Registro EMV`, `Escritura`, `Banda (fuzz)`); recablear los reexpones (`log_write`/`iso_response`/`emit_*`) al panel concreto. |
| `tests/test_gui.py` | `test_top_level_tabs` actualizado a la nueva lista; reemplazar cualquier assert de sub-tabs de `ToolsPanel`/`FuzzPanel` por asserts de Tabs de primer nivel; los tests de render (`_FlagsTool`, carriles) se re-apuntan al nuevo panel sin cambiar la lógica probada. |
| `tests/test_tui_fuzz.py`, `tests/test_tui_cobros_write.py` | **La TUI no se toca en Objetivo 1** (ADR-001/ADR-002 son de la GUI). Verificar que estos tests siguen verdes; no deberían verse afectados. |
| `CLAUDE.md §1, §5` | Actualizar la descripción de la GUI (paneles `tools`/`fuzz` → Tabs planos + nuevos grupos de sidebar). |

### 3.3 Enrutamiento / navegación afectada
- **`_NAV_GROUPS`** (`app.py:201-233`): reescribir los grupos EMVY (§3.1). Iconos: reutilizar los ya
  definidos en `emvy/gui/icons.py` (`{cpu, credit-card, download, flask, folder, home, nfc, play,
  plug, search, shield, sliders, square, wrench, zap}`); para `Emulación`/`Registro EMV`/`Banda`
  reutilizar `zap`/`credit-card`/`play` o **añadir SVG inline** a `icons.py` si se quiere iconografía
  propia (patrón ya establecido).
- **`addTab`** (`app.py:134-149`): una llamada por panel nuevo; la etiqueta debe coincidir con
  `_NAV_GROUPS`.
- **`_nav_to_tab`** (`app.py:243-256`): **no se toca** (une por etiqueta).
- **`_CONSOLE_TABS`** (`app.py:183-198`): sustituir `"Herramientas"`/`"Fuzzing"` por las etiquetas
  hijas que hagan IO serie; `Flags`/`ISO 8583` no necesitan consola (offline), pero incluirlas no
  rompe nada.

### 3.4 Sesiones (Objetivo 1)

- **Sesión O1-1 — Disolver `Herramientas`.** `tools.py` → 3 paneles; `app.py` wiring + regrupado
  parcial; `test_gui.py`. Bajo riesgo (los 3 tools ya son `QWidget` independientes).
- **Sesión O1-2 — Disolver `Fuzzing`.** `fuzz.py` → 4 paneles; centralizar estado compartido
  (fuente de tarjeta, Detener/Reboot); `app.py` wiring + grupo `EMULACIÓN`; `test_gui.py`. Mayor
  esfuerzo (los carriles comparten más estado). Resolver D-1 aquí.
- **Sesión O1-3 — Regrupado final + pulido.** Ajustar `_NAV_GROUPS` a §3.1, iconos, `_CONSOLE_TABS`,
  CLAUDE.md. Verificación headless (`QT_QPA_PLATFORM=offscreen`, `QWidget.grab()`).

Cada sesión deja `.venv/bin/python -m pytest tests/ -q` en verde.

---

## 4. Objetivo 2 — rebrand completo (detalle)

> Ejecutar **después** de Objetivo 1 (§10). Usa el token `⟨PKG⟩` = valor de D-0 (recom. `cardsec`).

### 4.1 Inventario de renombrados (actual → propuesto)

| Actual | Propuesto | Tipo |
|---|---|---|
| `emvy/` | `⟨PKG⟩/` | dir paquete |
| `emvyctl.py` | `⟨PKG⟩ctl.py` | módulo shim (distinto del dir paquete) |
| `packaging/EMVyController.spec` | `packaging/⟨PKG⟩.spec` | archivo |
| `packaging/emvy_gui.py` | `packaging/⟨PKG⟩_gui.py` | archivo |
| `packaging/emvy.svg` | `packaging/⟨PKG⟩.svg` | archivo |
| `firmware/EMVyBomberCat/` | `firmware/bombercat_multitool/` (D-4) | dir firmware |
| `firmware/EMVyBomberCat/EMVyBomberCat.ino` | `firmware/bombercat_multitool/bombercat_multitool.ino` | sketch (basename = carpeta) |
| `name="emvycontroller"` | `name="⟨PKG⟩"` | `pyproject.toml:2` |
| `emvyctl = "emvy.cli:main"` | `⟨PKG⟩ = "⟨PKG⟩.cli:main"` | `pyproject.toml:27-28` |
| `py-modules=["emvyctl"]`, `include=["emvy*"]` | `["⟨PKG⟩ctl"]`, `["⟨PKG⟩*"]` | `pyproject.toml:34-38` |
| `APP_NAME="emvy"` | `APP_NAME="⟨PKG⟩"` (+ migración D-2) | `config.py:13` |
| `EMVY_*` (5 vars) | `CARDSEC_*` (leer también las viejas) | env, §4.4 |
| Título/marca | "Card Security Suite" | `app.py:74,1384`, `__init__.py`, README, CLAUDE.md |

**No renombrar / regenerar:** `emvycontroller.egg-info/` y `.venv/**` (artefactos; se regeneran con
`uv pip install -e`). Añadir al `.gitignore` si no están.

### 4.2 Nueva estructura de directorios (raíz)

```
EMVy_Controller/
├── ⟨PKG⟩/                 (antes emvy/)
├── ⟨PKG⟩ctl.py            (antes emvyctl.py)
├── firmware/
│   ├── bombercat_multitool/   (antes EMVyBomberCat/)
│   ├── bombercat_emv_reader/  (sin cambio)
│   └── I2CDiscover/           (sin cambio)
├── packaging/
│   ├── ⟨PKG⟩.spec         (antes EMVyController.spec)
│   ├── ⟨PKG⟩_gui.py       (antes emvy_gui.py)
│   └── ⟨PKG⟩.svg          (antes emvy.svg)
├── tests/                 (imports reescritos)
├── vendor/                (sin cambio)
└── pyproject.toml         (name/scripts/find reescritos)
```

### 4.3 Comandos `git mv` (orden exacto)

> Ejecutar desde la raíz del repo, con árbol limpio (`git status` sin cambios sin commitear de
> Objetivo 1 ya commiteado). **Los `git mv` solo mueven; las ediciones de contenido van después
> (§4.4).** Sustituir `cardsec` por el valor D-0 si difiere.

```sh
# 0. Verificar árbol limpio antes de empezar
git status

# 1. Firmware (D-4). Borrar artefactos de build primero (se regeneran):
git rm -r firmware/EMVyBomberCat/build            # UF2/elf compilados, no fuente
git mv firmware/EMVyBomberCat firmware/bombercat_multitool
git mv firmware/bombercat_multitool/EMVyBomberCat.ino \
       firmware/bombercat_multitool/bombercat_multitool.ino

# 2. Paquete Python y shim
git mv emvy cardsec
git mv emvyctl.py cardsecctl.py

# 3. Packaging
git mv packaging/EMVyController.spec packaging/cardsec.spec
git mv packaging/emvy_gui.py          packaging/cardsec_gui.py
git mv packaging/emvy.svg             packaging/cardsec.svg

# 4. Commit del movimiento puro (histórico preservado), ANTES de editar contenido
git commit -m "rebrand: git mv de paquete/firmware/packaging (sin editar contenido)"
```

**Por qué este orden:** (1) el firmware es independiente del resto; (2) mover el paquete `emvy→
cardsec` antes de reescribir imports para que `git mv` registre el rename y el histórico siga cada
archivo; (3) commitear el mv **puro** por separado del sed de contenido hace que `git log --follow`
y el diff de revisión sean legibles (mover ≠ editar).

### 4.4 Actualizaciones de contenido tras el `git mv`

Hacer en un segundo commit. Orden:

1. **Imports Python** (183 líneas, ~37 archivos):
   ```sh
   grep -rlE '(from|import)[[:space:]]+emvy(\.|[[:space:]]|$)' --include='*.py' . \
     | grep -v '.venv' \
     | xargs sed -i -E 's/(from|import)([[:space:]]+)emvy(\.|[[:space:]]|$)/\1\2cardsec\3/g'
   ```
   Después, reemplazar referencias `emvy.` restantes en strings (p.ej. rutas de plugins en
   `poc/scaffold.py`, `poc/templates.py`) revisando `grep -rn 'emvy' --include='*.py' . | grep -v .venv`.

2. **`pyproject.toml`**: `name`, `[project.scripts]`, `py-modules`, `packages.find.include`
   (§4.1). El console-script pasa a `cardsec = "cardsec.cli:main"`.

3. **`config.py`** — `APP_NAME` + **migración D-2** + env vars:
   - `APP_NAME = "cardsec"`.
   - Nueva función `_migrate_legacy_data()` llamada perezosamente desde `data_home()`/`config_home()`
     (o una vez en `cli.main`/`run_gui`): si el destino nuevo no existe y el legacy
     (`~/.local/share/emvy`, `~/.config/emvy`) sí, **renombrar** el árbol una vez (log al usuario).
   - Env vars: leer **ambas** (`CARDSEC_ENGAGEMENTS` y, si ausente, `EMVY_ENGAGEMENTS`), ídem
     `CARDSEC_BOMBERCAT_TOOLS`/`EMVY_BOMBERCAT_TOOLS`. Documentar deprecación de las `EMVY_*`.

4. **Resto de env vars** (`EMVY_PROJECT` en `store.py:420-439`, `EMVY_GUI_KEEP_QT_ENV` en
   `app.py:1360-1364`, `EMVY_THEME` en `tui/app.py:20,145`): añadir lectura del nuevo nombre con
   fallback al viejo. Mantener el fallback al menos una versión (0.6.0) por compatibilidad.

5. **Marca/UI**: `__init__.py` (docstring, se puede subir `__version__`→`0.6.0` para marcar el corte),
   `app.py:74` (`setWindowTitle`), `app.py:1384` (`setApplicationName`), README banner, CLAUDE.md
   título (§1 y encabezado). El tema TUI `EMVY_THEME`/nombre de tema `"emvy"` en `tui/app.py`.

6. **Firmware refs**: `emvy/readers/bombercat.py` líneas 421,442,491,519,525,574 → cambiar el
   nombre en prosa "EMVyBomberCat" → "bombercat_multitool" (o el nombre visible que se elija). Son
   comentarios/docstrings/mensajes de error, **no** constantes de protocolo (el handshake serie no
   cambia; ver `docs/BomberCatControl-Discovery-Contract.md`).

7. **`packaging/`**: `cardsec.spec` (ENTRY `cardsec_gui.py`, icon `cardsec.ico`),
   `Dockerfile.appimage` (líneas 40-51: `import cardsec`, `cardsec.svg/png/desktop`, `Exec=`),
   `Dockerfile.windows`/`build-appimage.sh` (tags `cardsec-appimage`/`cardsec-win`, patrón AppImage
   `CardSec-*.AppImage`), `packaging/README.md`.

8. **Reinstalar editable y correr tests:**
   ```sh
   uv pip install --python .venv -e '.[dev,gui,tui]'   # regenera entry points / egg-info
   .venv/bin/python -m pytest tests/ -q
   ```

9. **Verificación funcional mínima:** `./cardsecctl.py readers`, `./cardsecctl.py tui` (humo),
   `./cardsecctl.py gui` (o headless `QT_QPA_PLATFORM=offscreen`). Confirmar que la migración XDG
   encontró los proyectos previos.

10. **Commit de contenido:**
    ```sh
    git commit -m "rebrand: reescribe imports, pyproject, env vars, marca y packaging a ⟨PKG⟩"
    ```

### 4.5 Sesiones (Objetivo 2)

- **Sesión O2-1 — Firmware + `git mv` puro.** Pasos §4.3 (1-4). Commit del mv sin editar contenido.
  Verificar que Arduino compila `bombercat_multitool` (`build.sh`) con el nuevo basename.
- **Sesión O2-2 — Imports + pyproject + reinstalación.** §4.4 (1-2, 8). Tests verdes con el paquete
  ya renombrado.
- **Sesión O2-3 — Config, migración XDG y env vars.** §4.4 (3-4). Test de `_migrate_legacy_data`
  con `XDG_*` en `tmp` (patrón `tests/test_project.py`). Test de fallback de env vars.
- **Sesión O2-4 — Marca, firmware-refs, packaging, docs.** §4.4 (5-7, 9). Verificación funcional.

---

## 5. Riesgos, dependencias y notas

- **Dependencia entre objetivos:** hacer **O1 antes de O2** (§10). Si se invierte, se renombraría
  `fuzz.py`/`tools.py` y luego se volverían a partir — churn evitable.
- **Migración XDG (D-2) es crítica:** sin ella el usuario "pierde" sus proyectos al actualizar. No
  omitir. Preferir **renombrar** el árbol (rápido, atómico) a copiar; si se copia, no borrar el
  legacy hasta confirmar.
- **Env vars son API de usuario:** romper `EMVY_PROJECT`/`EMVY_ENGAGEMENTS` afecta a engagements y
  scripts existentes. Mantener fallback ≥1 versión.
- **`sed` de imports puede tocar falsos positivos:** el patrón acota a `emvy` seguido de `.`/espacio/
  fin. Revisar el diff antes de commitear (`git diff --stat`, luego `git diff`). Ojo con literales
  `emvy` en comentarios/strings que NO son imports (revisar manualmente `grep -rn 'emvy'`).
- **Arduino basename:** el `.ino` debe llamarse igual que su carpeta o el IDE/`arduino-cli` no lo
  abre. Renombrar los dos (D-4) y actualizar `firmware/bombercat_multitool/build.sh`/`README.md` si
  referencian el nombre viejo.
- **Handshake serie NO cambia:** el protocolo (`ping → +OK bombercat`, `PING/WAIT/APDU:` …) es
  independiente del nombre del sketch; el rebrand del firmware es solo cosmético (nombre de carpeta
  + prosa). Ver `docs/BomberCatControl-Discovery-Contract.md`.
- **`EMV fuera de alcance` de ADR-001 (§8 del plan de firmwares):** Objetivo 1 reintroduce la
  superficie EMVY (emulación) como Tabs de primer nivel. Confirmar que la ruta
  `emvy/readers/bombercat.py` (passthrough/emulación) sigue operativa antes de exponerla; si sigue
  temporalmente incompatible, los Tabs `Emulación`/`Editor de tarjeta` pueden quedar visibles pero
  con aviso, como hoy.
- **CLAUDE.md es wiki viva:** actualizarla en ambos objetivos (arquitectura de GUI en O1; nombres/
  rutas en O2). El árbol `emvy/` de §1 de CLAUDE.md pasa a `⟨PKG⟩/`.

---

## 6. Orden global recomendado

1. **Objetivo 1** completo (Sesiones O1-1..O1-3) — deja el conjunto final de paneles/archivos GUI.
2. **Objetivo 2** completo (Sesiones O2-1..O2-4) — pasada de renombrado sobre ese conjunto.

Razón: O2 reescribe imports y (opcionalmente) renombra archivos de panel; hacerlo sobre el conjunto
ya estabilizado por O1 evita renombrar dos veces y mantiene los diffs de `git mv` legibles.

Cada sesión: tests verdes + GUI headless verificable. Commits pequeños; en O2, **separar el `git mv`
puro del `sed` de contenido** en commits distintos.

---

## 7. Referencias de código

- GUI wiring: `emvy/gui/app.py` (`_NAV_GROUPS:201`, `addTab:134`, `_nav_to_tab:243`,
  `_CONSOLE_TABS:183`, título:74, appName:1384).
- Paneles a disolver: `emvy/gui/panels/tools.py` (`ToolsPanel:43`), `emvy/gui/panels/fuzz.py`
  (`sub:50`, carriles `61/106/162/385`).
- Rutas/marca: `emvy/config.py:13`, `emvy/__init__.py:26`, `pyproject.toml`, `packaging/*`.
- Firmware: `firmware/EMVyBomberCat/`; refs en `emvy/readers/bombercat.py:421,442,491,519,525,574`.
- Patrón de referencia: `docs/Plan-Integracion-Firmwares-BomberCat.md` (ADR-001 + Progress log).
- Handshake: `docs/BomberCatControl-Discovery-Contract.md`.

---

## 8. Progress log

Registro cronológico por sesión. Cada entrada: qué quedó hecho, dónde, y desviaciones/hallazgos
respecto al plan, para que la siguiente sesión no re-descubra. (Vacío — plantilla debajo.)

### Sesión O1-1 — Disolver `Herramientas` — ✅ HECHO (2026-09-18)
- Orquestación/GUI: `emvy/gui/panels/tools.py` — `ToolsPanel(QTabWidget)` eliminado; `_FlagsTool`/
  `_IsoTool`/`_WriteTool` renombradas a `FlagsPanel`/`IsoPanel`/`WritePanel` (mismo `QWidget`, misma
  lógica interna, sin reescritura). `emvy/gui/app.py`: import actualizado; instancias
  `self.flags_panel`/`self.iso_panel`/`self.write_panel`; 3 `addTab` en lugar de uno; reexpones
  `write_op`/`send_iso8583` recableados a `self.write_panel.log_result` /
  `self.iso_panel.show_response` (ya no hay `setCurrentWidget` a un sub-tab — no aplica al ser Tabs
  de primer nivel; el comportamiento visible no cambia: antes tampoco cambiaba el Tab exterior).
  `_CONSOLE_TABS`: `"Herramientas"` → `"Escritura"` (Flags/ISO 8583 son offline, no necesitan
  consola). `_NAV_GROUPS`: grupo `TARJETA` pasa de `(Explorador, Herramientas)` a
  `(Explorador, Flags, ISO 8583, Escritura)` — **regrupado parcial**, el grupo `EMULACIÓN` de §3.1
  queda para O1-3 cuando `Fuzzing` también se disuelva. Iconos reusados: `search` (Flags),
  `credit-card` (ISO 8583), `wrench` (Escritura, el mismo que tenía "Herramientas").
- Tests: `tests/test_gui.py` — `test_tools_subtabs_and_iso_build` → `test_tools_panels_and_iso_build`
  (usa `win.iso_panel` directo, sin `tabText`/`count` de sub-tabs); `test_top_level_tabs` actualizado
  a la nueva lista de 18 Tabs (Flags/ISO 8583/Escritura en vez de Herramientas). Suite completa:
  `.venv/bin/python -m pytest tests/ -q` → 233 passed, 11 skipped. Verificación headless adicional
  (`QT_QPA_PLATFORM=offscreen`, instanciar `MainWindow`, volcar `nav`/`tabs`) confirma barra lateral
  y Tabs con la estructura esperada.
- Desviaciones: ninguna respecto al plan. `CLAUDE.md` actualizado (árbol de arquitectura §1 línea del
  `panels/` de GUI, descripción de la GUI en §5, `_CONSOLE_TABS` en la nota de limpieza contextual).
  La TUI no se tocó (fuera de alcance de Objetivo 1, confirmado sin efectos: sus tests siguen verdes).

### Sesión O1-2 — Disolver `Fuzzing` — ✅ HECHO (2026-09-18)
- Orquestación/GUI: `emvy/gui/panels/fuzz.py` — `FuzzPanel(QWidget)` con `QTabWidget` interno
  eliminado; los 4 carriles se separaron en paneles `QWidget` de primer nivel (mismo cuerpo,
  sin reescritura de lógica): `_track_lane`→`MagfuzzPanel`, `_emv_lane`→`EmvRecordPanel`,
  `_ndef_lane`→`EmulationPanel`, `_card_editor`→`CardEditorPanel`. No había estado compartido
  real entre carriles más allá de `self.win` (cada uno usa sus propios atributos `_track_*`/
  `_emv_*`/`_ndef_*`/`_ed_*`), así que no hizo falta extraer un mixin — cada clase quedó
  autocontenida, igual que `FlagsPanel`/`IsoPanel`/`WritePanel` en O1-1. Cada panel añade su
  propia advertencia (`_warn()`, antes una sola compartida en el contenedor). D-1 resuelto:
  `MagfuzzPanel` (fuzzing de banda, plantillas mutadas) se mantiene como Tab propio, distinto
  del panel `Magspoof` (HW, operación del store) — incluido en el grupo `EMULACIÓN` de la
  barra lateral, no en `HARDWARE`.
  `emvy/gui/app.py`: import actualizado (`CardEditorPanel, EmulationPanel, EmvRecordPanel,
  MagfuzzPanel`); instancias `self.card_editor_panel`/`self.emulation_panel`/
  `self.emv_record_panel`/`self.magfuzz_panel`; 5 `addTab` (Editor de tarjeta/Emulación/
  Registro EMV/Escritura/Banda (fuzz)) en vez de uno para "Fuzzing" — `Escritura`
  (`WritePanel`, ya disuelto en O1-1) se **reubicó** de la lista de tabs entre ISO 8583 y
  Cobros a entre Registro EMV y Banda (fuzz), agrupada con el resto de EMULACIÓN. Los dos
  reexpones que apuntaban a `self.fuzz_panel` se recablearon: `refresh_all()` →
  `self.emulation_panel._reload_captures()`; `_fill_card_editor()` →
  `self.card_editor_panel._ed_populate(card)`. `dashboard.py`: los dos accesos rápidos que
  navegaban a `_go("Fuzzing")` ahora van a `_go("Emulación")` (label "Ir a Emulación").
  **Regrupado ya incluido aquí** (no se dejó para O1-3, evita tocar `_NAV_GROUPS` dos veces):
  `_NAV_GROUPS` pasó de `(SESIÓN, TARJETA, OPERACIONES, HARDWARE)` a la estructura final de
  §3.1 — `TARJETA`→`ANÁLISIS` (Explorador/Flags/ISO 8583, sin Escritura) + grupo nuevo
  `EMULACIÓN` (Editor de tarjeta/Emulación/Registro EMV/Escritura/Banda (fuzz)) +
  `OPERACIONES` sin Fuzzing (Cobros/PoC/Intercept). Iconos: `credit-card` (Editor de
  tarjeta), `zap` (Emulación, el mismo que tenía "Fuzzing"), `download` (Registro EMV),
  `play` (Banda (fuzz)); `wrench` para Escritura sin cambio. `_CONSOLE_TABS`: `"Fuzzing"` →
  las 4 etiquetas hijas que hacen IO serie (`Editor de tarjeta`, `Emulación`, `Registro EMV`,
  `Banda (fuzz)`), `Escritura` ya estaba.
- Estilo: `emvy/gui/theme.py` — comentario de `QTabBar` desactualizado (mencionaba
  "Herramientas, Fuzzing" como sub-pestañas internas, ya no existen) corregido.
- Tests: `tests/test_gui.py` — todos los `fz = win.fuzz_panel` recableados al panel concreto
  (`win.emulation_panel` para los tests de fuente NDEF/EMV y emit; `win.card_editor_panel`
  para los tests del editor; `test_fuzz_track_and_emv_generate` se separó en `mag =
  win.magfuzz_panel` + `rec = win.emv_record_panel` porque mezclaba los dos carriles).
  `test_top_level_tabs` actualizado a la lista de 21 Tabs (sin "Fuzzing"; con Editor de
  tarjeta/Emulación/Registro EMV/Banda (fuzz) intercalados). Suite completa:
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q` → 233 passed, 11 skipped.
  Verificación headless adicional (volcado de `nav`/`tabs`) confirma la barra lateral
  agrupada (`SESIÓN/ANÁLISIS/EMULACIÓN/OPERACIONES/HARDWARE`) y el gateo de
  `_CONSOLE_TABS`.
- Documentación: `CLAUDE.md` — párrafo "GUI de escritorio" (§5) reescrito para reflejar los
  Tabs planos y `_NAV_GROUPS` actual; árbol de arquitectura (§1, línea de `panels/`) y las
  menciones de §9 a "pestaña Fuzzing" distinguidas por frontend (TUI conserva su pestaña
  Fuzzing con sub-pestañas propias — fuera de alcance; GUI ahora dice "Emulación").
- Desviaciones respecto al plan: **el regrupado final de `_NAV_GROUPS` (nominalmente de
  O1-3) se hizo en esta sesión**, no solo el "grupo EMULACIÓN" — se aplicó también el
  renombrado `TARJETA`→`ANÁLISIS` y el traslado de `Escritura`, porque separarlo en dos
  pasadas habría tocado la misma tupla dos veces sin motivo (el mismo argumento que ya usa
  §6 del plan para no invertir el orden de Objetivo 1/Objetivo 2). O1-3 queda reducido a:
  confirmar que no falta pulido de iconografía, y el resto de la lista de §3.4 (que ya
  quedó cubierta aquí). La TUI no se tocó (fuera de alcance de Objetivo 1, sus tests siguen
  verdes sin cambios).

### Sesión O1-3 — Regrupado + pulido — ✅ HECHO (2026-09-18)
- Revisión de `CLAUDE.md`: no había menciones residuales de "11 pestañas"/`_apply_tab_icons`
  (esa referencia vivía solo en código, ver debajo); la única mención de "sub-pestañas" que
  queda (`CLAUDE.md:285`, sección `### TUI`) es correcta — la TUI conserva su `ToolsScreen`
  con sub-pestañas propias, fuera de alcance de Objetivo 1 (confirmado en O1-2).
- Hallazgo real (no en el plan original): `emvy/gui/app.py:165` tenía un comentario obsoleto
  ("Navegación por barra lateral, más limpia que 11 pestañas arriba") de antes de O1-1/O1-2,
  cuando la GUI tenía 11 Tabs; hoy son 21. Reescrito a una frase que no requiere mantener un
  número ("más limpia que todas las pestañas arriba") para que no vuelva a quedar desactualizado.
- Pulido de iconografía: `_NAV_GROUPS` tenía dos etiquetas **adyacentes** con el mismo icono
  dentro del grupo `ANÁLISIS` (`Explorador`/`Flags`, ambas `"search"`) — inconsistente con el
  resto de grupos (sin duplicados adyacentes). Añadido un icono propio `"flag"` (bandera,
  trazo Lucide) a `emvy/gui/icons.py::_PATHS` y reasignado a la pestaña `Flags`
  (`app.py::_NAV_GROUPS`), temáticamente más preciso (busca flags de CTF) que reusar `search`.
  El resto de repeticiones de icono (`credit-card` ×4, `shield` ×2, `search` ×2 tras el cambio)
  quedan entre grupos **distintos**, no adyacentes en la barra — no ameritan más SVGs nuevos
  (evitar iconografía especulativa sin necesidad visual real).
- Verificación: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q` → 233 passed,
  11 skipped (sin regresiones). Verificación headless adicional instanciando `MainWindow`:
  21 Tabs, 26 filas de nav (5 encabezados de grupo + 21 items), todos los iconos resuelven
  (`icon-ok`) incluido el nuevo `flag`.
- Objetivo 1 queda **completo** (O1-1, O1-2, O1-3). Siguiente: Objetivo 2 (rebrand, §4),
  empezando por la Sesión O2-1.

### Sesión O2-1 — Firmware + `git mv` puro — ✅ HECHO (2026-09-18)
- **D-0 confirmado con el usuario**: `cardsec` (paquete `cardsec/`, CLI `cardsec`, shim
  `cardsecctl.py`, distribución `cardsec`, producto "Card Security Suite", env `CARDSEC_*`).
  El resto de Objetivo 2 usa este nombre, no una variable abierta.
- **Árbol no estaba limpio** (`CLAUDE.md` modificado + 3 `docs/*.md` nuevos + `uv.lock` sin
  trackear, de trabajo previo de sesión no commiteado). Decisión del usuario: **no commitearlos
  aparte**, dejarlos fuera del stage. El commit del `git mv` (`1a94c48`) solo contiene los
  renombrados — `git mv` deja el resto del árbol intacto, así que el commit resultante es
  igual de "puro" que si el árbol hubiera estado limpio (verificado con `git status` antes de
  commitear: `CLAUDE.md`/`docs/*.md`/`uv.lock` seguían fuera de stage).
- `git rm -r firmware/EMVyBomberCat/build` (borra el `.uf2` precompilado, no es fuente) →
  `git mv firmware/EMVyBomberCat firmware/bombercat_multitool` → `git mv
  firmware/bombercat_multitool/EMVyBomberCat.ino firmware/bombercat_multitool/bombercat_multitool.ino`
  (D-4) → `git mv emvy cardsec` → `git mv emvyctl.py cardsecctl.py` → `git mv
  packaging/EMVyController.spec packaging/cardsec.spec` → `git mv packaging/emvy_gui.py
  packaging/cardsec_gui.py` → `git mv packaging/emvy.svg packaging/cardsec.svg`. Los 108 archivos
  del paquete `emvy/` (incl. todos los submódulos `core/gui/tui/payments/poc/project/readers/
  session/integrations`) se movieron con `git mv` directo sobre el directorio — Git detecta cada
  archivo interno como rename 100% individual (confirmado en `git status`/`git log --stat`).
  Commit `1a94c48` — solo movimientos, sin edición de contenido (§4.3 respetado).
- **Verificación de compilación real** (más allá de lo pedido por §4.5, que solo pedía
  verificar): `arduino-cli` disponible en el entorno (`1.5.1`); `./firmware/bombercat_multitool/
  build.sh` compiló limpio contra `electroniccats:mbed_rp2040:bombercat` (162 702 bytes de
  programa, 7%) y generó `build/bombercat_multitool.ino.{bin,elf,hex,map}` — el basename nuevo
  (`bombercat_multitool.ino` = nombre de carpeta) es válido para arduino-cli, confirmando D-4.
  Sin `.uf2` en la salida — **comportamiento ya conocido y documentado** (CLAUDE.md §12: esta
  placa no genera `.uf2` desde `arduino-cli compile`, se sube por picotool o se convierte el
  `.elf` con `elf2uf2`), no una regresión del rename. `build.sh` conserva el comentario "EMVyBomberCat"
  en su cabecera (línea 2) — contenido, no movimiento; queda para la sesión O2-4 (§4.4.6) que ya
  cubre las refs en prosa a "EMVyBomberCat". Artefactos de compilación quedan bajo
  `firmware/bombercat_multitool/build/` (ignorados por `.gitignore:36-37` salvo `.uf2`; no ensucian
  el árbol de git — confirmado con `git status --short firmware/`).
- Desviaciones respecto al plan: ninguna en el `git mv` en sí. La única diferencia es que el
  árbol no estaba estrictamente limpio al empezar (ver arriba) — decisión explícita del usuario,
  no un olvido; el commit resultante sigue siendo puro movimiento. Siguiente: Sesión O2-2
  (imports + `pyproject.toml` + reinstalación, §4.4 puntos 1-2 y 8).

### Sesión O2-2 — Imports + pyproject — ✅ HECHO (2026-09-18)
- **Imports** (§4.4.1): `grep -rlE '(from|import)\s+emvy(\.|\s|$)' --include='*.py' . | grep
  -v .venv | xargs sed -i -E 's/(from|import)(\s+)emvy(\.|\s|$)/\1\2cardsec\3/g'` sobre los 34
  archivos detectados (todos bajo `cardsec/`, `tests/`, `cardsecctl.py`, `packaging/cardsec_gui.py`);
  verificado sin coincidencias tras el `sed`.
- **Prosa/strings con rutas de módulo o comandos CLI** (revisión manual de `grep -rn 'emvy'
  --include='*.py'`, como pide el plan): corregidas todas las menciones `emvy.xxx` → `cardsec.xxx`
  en docstrings (`cardsec/__init__.py`, `cardsec/tui/__init__.py`, `cardsec/poc/scaffold.py`,
  `cardsec/poc/templates.py`, `cardsec/config.py:44`, `conftest.py`, `tests/fakeserial.py`,
  `tests/test_payments.py`, `tests/test_pcscd.py`) y todos los hints de uso `emvy <subcomando>` →
  `cardsec <subcomando>` en `cardsec/cli.py` (prompt del shell interactivo, `prog="emvyctl"` →
  `prog="cardsec"`, ~15 mensajes `print()`/`raise` que citaban el comando), `cardsec/poc/model.py`,
  `cardsec/integrations/bombercat_tools.py`, `cardsec/integrations/pcscd.py`. También renombrado el
  prefijo interno `emvy_poc_plugin_` → `cardsec_poc_plugin_` en `cardsec/poc/registry.py` (namespace
  de `sys.modules` para plugins, sin dependientes externos).
  **Fuera de alcance (dejado tal cual, corresponde a sesiones posteriores)**: todo lo que depende de
  `APP_NAME`/rutas XDG (`~/.local/share/emvy`, `<XDG_DATA_HOME>/emvy/...` en `config.py`,
  `store.py`, `gui/panels/projects.py`, `tui/screens/projects.py`, `packaging/cardsec_gui.py`), el
  nombre del tema TUI `"emvy"` (`tui/app.py`), branding "EMVyController" (`cli.py`, `__init__.py`),
  el prefijo de archivo `emvy-consola-*.log` (`gui/panels/console.py`) y la URL/texto de prueba
  `emvy.test`/`"EMVy fuzz"` (`core/cardfuzz.py` + su test) — todos explícitamente de §4.4 puntos
  3-7 (O2-3/O2-4).
- **`pyproject.toml`** (§4.4.2): `name` → `"cardsec"`; `[project.scripts]` → `cardsec =
  "cardsec.cli:main"` (antes `emvyctl = "emvy.cli:main"` — el nombre del entry-point pasa de
  `emvyctl` a `cardsec`, distinto del shim `cardsecctl.py`); `py-modules` → `["cardsecctl"]`;
  `packages.find.include` → `["cardsec*"]`.
- **CI** (no listado explícitamente en el plan, pero roto por el rename y parte de "tests
  verdes"): `.github/workflows/tests.yml` — `paths: emvy/**` → `cardsec/**` (×2, push y
  pull_request), `emvyctl --help` → `cardsec --help`, `coverage run --source=emvy` → `--source=cardsec`.
- **Reinstalación** (§4.4.8): `uv pip install --python .venv -e '.[dev,tui]'` → instala `cardsec
  0.5.0` con entry-point `cardsec` (verificado `./.venv/bin/cardsec --help` — `prog: cardsec`).
  Artefactos obsoletos del venv limpiados a mano (no los regenera `uv pip install -e`):
  `emvycontroller.egg-info/` (raíz) y `.venv/bin/emvyctl` (script viejo); ambos fuera de git
  (`*.egg-info/` en `.gitignore`).
- **Hallazgo no previsto en el plan**: `.venv/bin/python -m pytest tests/ -q` con el árbol ya
  renombrado dio **2 fallos** — `tests/test_firmware_sources.py::test_list_sketches_and_compile` y
  `tests/test_gui.py::test_firmware_lists_sketches` — ambos aserciones literales `"EMVyBomberCat"`
  contra `ard.list_sketches()`/el combo de sketches de la GUI, que ya no existe como carpeta desde
  el `git mv firmware/EMVyBomberCat → firmware/bombercat_multitool` de la **Sesión O2-1**. O2-1 no
  dejó registrado en su log haber corrido la suite completa tras el `git mv` (solo verificó
  `build.sh`), así que esta regresión llevaba pendiente desde esa sesión sin detectarse. Corregidas
  aquí (no es "marca"/branding, es la verdad funcional del nombre de carpeta ya vigente): ambas
  aserciones → `"bombercat_multitool"`.
- **Verificación final**: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q` → **270
  passed** (0 failed, 0 skipped — antes de esta sesión el run de referencia de O1-3 era "233 passed,
  11 skipped"; el conteo distinto no se investigó más allá de confirmar que no hay fallos, no parece
  relacionado con los cambios de esta sesión).
- **No se commiteó nada**: por diseño del plan (§4.4 punto 10), el commit de contenido del rebrand
  es **uno solo al final de todo Objetivo 2** (tras O2-4), no por sesión — así que estos cambios
  quedan en el árbol de trabajo. Siguiente: Sesión O2-3 (config, migración XDG D-2, fallback de
  las 5 env vars `EMVY_*`, §4.4 puntos 3-4).

### Sesión O2-3 — Config + migración XDG + env vars — ⬜ PENDIENTE
- …

### Sesión O2-4 — Marca + packaging + docs — ⬜ PENDIENTE
- …
