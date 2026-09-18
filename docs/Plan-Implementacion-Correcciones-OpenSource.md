# Plan de implementación — correcciones OpenSource y preparación upstream

**Estado:** En ejecución — v1.1 (2026-09-18). Fases A, B y C completadas (Sesiones 1–9);
pendiente Fase D (Sesiones 10–11). Ver §7 Progress log.
**Alcance:** ejecutar de forma **iterativa y verificable** las correcciones derivadas del análisis
de buenas prácticas OpenSource sobre los dos planes de referencia, registrando el progreso, la
**validación de valor** de cada cambio, y el **cumplimiento OSS** para facilitar la contribución
upstream a `Glitchboi-sudo/EMVy_Controller`.
**Audiencia:** desarrolladores del repo que ejecutarán estas sesiones y actualizarán el progress log.

> Written for: desarrolladores del repo. Asume familiaridad con `emvy/gui/` (PySide6),
> `emvy/config.py`, `pyproject.toml`, la licencia AGPL-3.0 del proyecto, y con los dos planes de
> referencia citados abajo.

**Documentos de referencia (fuente de verdad de los cambios técnicos):**
- `docs/Plan-Reestructuracion-EMVY-y-Rebrand.md` — reestructuración de Tabs (Objetivo 1, ejecutado)
  + rebrand `emvy → cardsec` (Objetivo 2, parcialmente ejecutado).
- `docs/Plan-Integracion-Firmwares-BomberCat.md` — integración de firmwares oficiales en la GUI
  (Sesiones 1–5 + refactor ADR-001, completas).

> **Cómo usar este documento:** cada sesión (§3) es una unidad de trabajo discreta con criterios de
> aceptación. Al terminarla, actualiza la fila correspondiente del **Progress log** (§7) y añade el
> bloque detallado usando el **template** (§10). No borres información de los planes de referencia:
> este plan los **corrige y ordena**, no los sustituye.

---

## 1. Resumen ejecutivo

### 1.1 Objetivo
Alinear el fork con las buenas prácticas de código abierto de forma que **cada cambio (a) agregue
valor real, (b) cumpla la licencia AGPL-3.0 y las convenciones OSS, y (c) no dañe —idealmente
facilite— la capacidad de contribuir upstream** a `Glitchboi-sudo/EMVy_Controller`.

### 1.2 Contexto verificado (no asumido)
| Hecho | Valor | Implicación |
|---|---|---|
| `origin` | `ElectronicCats/Bombercat-GUI` | No es el padre declarado. |
| Padre declarado | `Glitchboi-sudo/EMVy_Controller` | Destino de los PRs upstream. |
| Remote `upstream` | **no configurado** | Hoy no se puede sincronizar con el padre. |
| Licencia | **AGPL-3.0-or-later**, `Copyright © 2026 glitchboi` | Obliga a conservar avisos de autoría y origen. |
| Rebrand (Objetivo 2) | **Commiteado en `feature/refactor`** (5 commits); `origin/main` sigue limpio en `emvy/` (`name="emvycontroller"`) | El rebrand `emvy → cardsec` NO está a medias ni sin commit: está en la rama de trabajo, mezclado con trabajo aditivo. README/CONTRIBUTING/CHANGELOG siguen atribuyendo a Glitchboi → **estado híbrido incoherente** en la rama de producto. |
| Gobernanza | `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `.github/`, pre-commit, CI, 238+ tests | Base OSS sólida ya presente. |

### 1.3 Hallazgo central que gobierna el plan
Los dos planes empujan en direcciones opuestas:
- **Rebrand `emvy → cardsec`** → maximiza la divergencia con el padre.
- **Contribuir la integración BomberCat upstream** → exige minimizar la divergencia.

Renombrar el paquete y reescribir 183 imports hace **inmergeable** cualquier PR contra un upstream
donde el paquete sigue siendo `emvy/`. Por tanto la **Sesión 1 es una compuerta de decisión**
(`D-CORE`) que condiciona el resto del plan.

### 1.4 Principios OpenSource que guían la implementación
1. **Cumplimiento de licencia primero.** Nada se publica/renombra sin preservar la autoría y el
   origen exigidos por la AGPL-3.0.
2. **Cada cambio justifica su valor.** Si un cambio no agrega valor demostrable al usuario o al
   mantenimiento, no se ejecuta (se marca "sin valor" en la auditoría §2).
3. **Divergencia mínima con upstream** salvo decisión explícita de hard-fork.
4. **Cambios pequeños, aditivos y con tests verdes.** Nada de PRs monolíticos.
5. **Trazabilidad:** ADRs para decisiones, CHANGELOG para cambios visibles, commits semánticos.
6. **Coherencia documental:** README, CONTRIBUTING, CHANGELOG, pyproject y CLAUDE.md cuentan la
   misma historia.

---

## 2. Auditoría de valor de los planes de referencia

Clasificación explícita de qué cambios propuestos **agregan valor**, cuáles son **neutros/cosméticos**
y cuáles tienen **valor negativo** (dañan mantenibilidad o contribución upstream). Esta tabla es la
base para decidir qué se ejecuta y qué se descarta o aísla.

| Cambio (origen) | ¿Valor? | Veredicto y razón |
|---|---|---|
| Integración firmwares oficiales en GUI (Plan Integración, todo) | **Alto** | Aditivo, aislado, con tests canned. Candidato ideal a PR upstream. **Ejecutar/conservar.** |
| Refactor ADR-001 (un Tab por firmware) | **Alto** | Mejora descubribilidad; decisión de diseño defendible y documentada. **Conservar.** |
| Objetivo 1 — aplanar sub-tabs EMVY (ADR-002) | **Medio-Alto** | Consistencia UX real. Valor propio; ofrecible upstream como PR separado. **Conservar.** |
| Migración XDG (D-2, `_migrate_legacy_data`) | **Alto (condicional)** | Protege datos del usuario. Solo relevante **si** hay rebrand. **Conservar si D-CORE = hard-fork.** |
| Alias de compatibilidad `EMVY_*` env vars | **Medio (condicional)** | Evita romper scripts de usuario. Solo si hay rebrand. **Conservar si hard-fork.** |
| Rebrand `emvy → cardsec` (Objetivo 2 completo) | **Negativo para upstream / condicional para producto** | Inmergeable upstream; riesgo AGPL si no preserva atribución. **Solo si D-CORE = hard-fork, y con §Sesión 2.** |
| Rename firmware `EMVyBomberCat → bombercat_multitool` (D-4) | **Bajo/cosmético** | No cambia protocolo (handshake serie intacto). Complica upstream si el sketch se contribuye. **Diferir; decidir en D-CORE.** |
| Nombre neutro "cardsec"/"Card Security Suite" (D-0) | **Cuestionable** | Desalinea de la marca BomberCat/ElectronicCats que da sentido a la GUI. **Reabrir decisión (§Sesión 1).** |

> **Regla:** ningún cambio "Negativo para upstream" o "cuestionable" se ejecuta o se mantiene
> commiteado en `main`/`feature/refactor` hasta que `D-CORE` (§Sesión 1) esté resuelta.

---

## 3. Sesiones de trabajo

Cada sesión deja `.venv/bin/python -m pytest tests/ -q` en verde y (donde aplique) GUI verificable
headless (`QT_QPA_PLATFORM=offscreen`, `QWidget.grab()`). Fases ordenadas por dependencia.

### Fase A — Decisión y gobernanza (desbloquea todo)

#### Sesión 1 — Compuerta de decisión `D-CORE`: fork-contribución vs. hard-fork
- **Descripción:** resolver formalmente la naturaleza del proyecto, porque determina si el rebrand
  se completa, se aísla o se revierte.
- **Objetivos:**
  - Decidir entre **(A) fork-contribución** (se prioriza aportar upstream; NO rebrand en la línea
    principal) y **(B) hard-fork/producto propio** (rebrand permitido, con obligaciones AGPL).
  - Consultar a los actores implicados: dueño de `origin` (ElectronicCats) y autor del padre
    (Glitchboi) — al menos notificar la intención.
  - Reabrir **D-0** (nombre): ¿neutro "cardsec" o alineado a BomberCat/ElectronicCats?
- **Cambios propuestos:** registrar la decisión como **ADR-003** en este documento (§9) y en
  `CLAUDE.md`. Ajustar la tabla de auditoría (§2) según el resultado.
- **Criterios de aceptación:** ADR-003 escrito con contexto, decisión, justificación y
  consecuencias; D-0 confirmada o reabierta con responsable; los actores han sido notificados
  (enlace a issue/hilo).
- **Complejidad:** Baja (esfuerzo) / **Crítica** (impacto). Bloquea Sesiones 5, 10, 11.

#### Sesión 2 — Cumplimiento AGPL y atribución
- **Descripción:** garantizar que el estado actual (y cualquier rebrand) respeta la sección 5 de la
  AGPL-3.0 (avisos de copyright y de origen del trabajo modificado).
- **Objetivos:** preservar y hacer prominente la autoría original de Glitchboi, resolver el estado
  híbrido incoherente detectado en §1.2.
- **Cambios propuestos:**
  - Añadir archivo **`NOTICE`** (o sección en README): "Este proyecto es un derivado de
    [EMVy Controller](https://github.com/Glitchboi-sudo/EMVy_Controller) de Glitchboi, © 2026
    glitchboi, distribuido bajo AGPL-3.0-or-later."
  - `pyproject.toml`: `authors` debe **seguir incluyendo** a glitchboi (añadir mantenedores en
    `maintainers` si aplica), aunque `name` haya cambiado.
  - Coherencia: `CONTRIBUTING.md`, `CHANGELOG.md`, README y `pyproject` deben contar la misma
    historia (fork de quién, mantenido por quién, bajo qué nombre).
- **Referencia:** análisis §2/§3 del informe; `LICENSE`; Plan-Reestructuración §4.1 (marca).
- **Criterios de aceptación:** `NOTICE` presente; ningún archivo elimina el crédito original; los 5
  documentos de gobernanza son mutuamente consistentes; `grep -rn 'glitchboi\|Glitchboi'` muestra
  atribución intacta y coherente.
- **Complejidad:** Baja. **Obligatoria e independiente de D-CORE** (aplica en ambos caminos).

#### Sesión 3 — Configurar `upstream` y flujo de sincronización
- **Descripción:** habilitar la sincronización con el repo padre, hoy imposible por falta de remote.
- **Objetivos:** poder traer mejoras del padre y medir la divergencia real.
- **Cambios propuestos:**
  ```sh
  git remote add upstream https://github.com/Glitchboi-sudo/EMVy_Controller.git
  git fetch upstream
  ```
  Documentar en `CONTRIBUTING.md` el flujo (`git fetch upstream` + `merge`/`rebase` periódico) y
  corregir la URL de `git clone` (hoy apunta a Glitchboi; alinear con la decisión D-CORE).
- **Criterios de aceptación:** `git remote -v` muestra `upstream`; `CONTRIBUTING.md` documenta el
  flujo de sync; `git log --oneline upstream/main ^HEAD | wc -l` documentado como línea base de
  divergencia.
- **Complejidad:** Baja.

### Fase B — Auditoría de valor de lo ya ejecutado

#### Sesión 4 — Validar el valor de Objetivo 1 (reestructuración de Tabs)
- **Descripción:** Objetivo 1 ya está ejecutado (O1-1..O1-3). Confirmar que agregó valor y que es
  ofrecible upstream por separado.
- **Objetivos:** verificar UX (descubribilidad), tests verdes, y aislar el diff para un posible PR.
- **Cambios propuestos:** ninguno de código si todo está correcto; producir un **resumen de diff**
  (`git diff upstream/main -- emvy/gui/`) y una nota para reviewers (§5).
- **Criterios de aceptación:** suite verde; diff de Objetivo 1 identificado y separable; anotado en
  §2 como "conservar".
- **Complejidad:** Baja.

#### Sesión 5 — Decidir destino del rebrand (Objetivo 2) según `D-CORE`
- **Descripción:** el rebrand está a medias en el árbol de trabajo (sin commit final). Actuar según
  el resultado de la Sesión 1.
- **Objetivos:**
  - **Si D-CORE = fork-contribución:** **revertir/aislar** el rebrand a una rama de producto
    separada; la línea principal vuelve a `emvy/`.
  - **Si D-CORE = hard-fork:** **completar** el rebrand (Sesiones O2-3/O2-4 del plan de referencia)
    **con** la atribución de la Sesión 2 y la migración XDG (D-2).
- **Cambios propuestos:** ver Plan-Reestructuración §4.4 (puntos 3–7) y §4.5 (O2-3/O2-4).
- **Criterios de aceptación (hard-fork):** migración XDG testeada (`_migrate_legacy_data` con
  `XDG_*` en `tmp`); fallback de env vars testeado; `NOTICE` presente; suite verde; verificación
  funcional (`./<pkg>ctl.py readers/tui/gui`).
  **Criterios (fork-contribución):** `main` sin renombrados; rebrand vive solo en rama aparte;
  suite verde con paquete `emvy`.
- **Complejidad:** Media-Alta. **Depende de Sesión 1.**

### Fase C — Endurecimiento de la integración de firmwares

#### Sesión 6 — Matriz de compatibilidad de versiones
- **Descripción:** hacer explícita la compatibilidad hoy implícita en `PINNED_TAG = v1.3.0`.
- **Objetivos:** que la comunidad sepa qué versión de `bombercat-tools` y qué firmwares `.uf2`
  soporta cada release.
- **Cambios propuestos:** tabla en README/wiki: `release del proyecto ↔ bombercat-tools tag ↔
  firmwares .uf2 soportados`. Referencia: Plan-Integración §8, §12.
- **Criterios de aceptación:** tabla presente y enlazada desde CLAUDE.md §12; coincide con
  `.gitmodules`/`PINNED_TAG`.
- **Complejidad:** Baja.

#### Sesión 7 — Condición de salida del firmware EMV "fuera de alcance"
- **Descripción:** el firmware EMV propio quedó "temporalmente incompatible" sin criterio de
  reactivación (Plan-Integración §8).
- **Objetivos:** que "temporal" tenga condición de salida explícita.
- **Cambios propuestos:** issue con criterios de reactivación **o** marcarlo `deprecated`
  formalmente en CLAUDE.md §9 + CHANGELOG.
- **Criterios de aceptación:** estado del firmware EMV documentado sin ambigüedad; issue creado o
  deprecación registrada.
- **Complejidad:** Baja.

#### Sesión 8 — Robustez de parsers `rich` + test de contrato por versión
- **Descripción:** varios helpers dependen de literales exactos de la salida `rich` del vendor
  (riesgo señalado en Plan-Integración Sesión 5, desviación 4: `"APDU pairs relayed"`).
- **Objetivos:** reducir la fragilidad del *scraping* de stdout.
- **Cambios propuestos:** consolidar parsers (`parse_status`/`parse_relay_*`/`_table_rows`) en un
  módulo con un test de contrato contra salida canned **por versión del vendor**, y un aviso claro
  cuando el venv del vendor no está listo (que el skip no oculte deriva real). Ref: Plan-Integración
  §4, §10 (Sesión 1 desviación 3, Sesión 5 desviación 4).
- **Criterios de aceptación:** parsers en un único punto; test de contrato no se salta silenciosamente
  sin avisar; suite verde.
- **Complejidad:** Media.

#### Sesión 9 (opcional) — Streaming cancelable §7.2 o marcarlo "no planeado"
- **Descripción:** `watch/monitor/flash/scan/capture` se resolvieron con timeouts, no streaming
  cancelable real (Plan-Integración §7.2, pendiente flotante).
- **Objetivos:** cerrar el pendiente: implementarlo o declararlo fuera de alcance.
- **Cambios propuestos:** variante de orquestador con emisión por líneas cancelable **o** nota en
  CLAUDE.md marcándolo "no planeado".
- **Criterios de aceptación:** §7.2 deja de ser un pendiente sin dueño.
- **Complejidad:** Media-Alta (si se implementa) / Baja (si se descarta).

### Fase D — Preparación upstream (solo si D-CORE = fork-contribución, o para el brazo de contribución del hard-fork)

#### Sesión 10 — Rama `upstream-clean` sin rebrand
- **Descripción:** preparar la base limpia para los PRs.
- **Objetivos:** una rama partida de `upstream/main` con **solo** cambios aditivos sobre `emvy/`.
- **Cambios propuestos:** `git checkout -b upstream-clean upstream/main`; cherry-pick/reaplicar la
  integración BomberCat y (opcionalmente) Objetivo 1, **sin** ningún renombrado.
- **Criterios de aceptación:** la rama compila y pasa tests con el paquete `emvy`; `git diff
  upstream/main` no contiene renombrados masivos.
- **Complejidad:** Media. **Depende de Sesiones 1 y 5.**

#### Sesión 11 — Trocear en PRs + issue de propuesta + dependencia vendor opcional
- **Descripción:** convertir el trabajo en PRs pequeños y aceptables.
- **Objetivos:** maximizar probabilidad de aceptación upstream.
- **Cambios propuestos:**
  - Abrir **issue de propuesta** en `EMVy_Controller` (qué/por qué, enlazando ADR-001).
  - PR 1: helpers de orquestador (`bombercat_tools`) + tests canned.
  - PR 2: paneles GUI de firmwares (ADR-001).
  - PR 3 (opcional): refactor de Tabs (ADR-002).
  - Hacer la dependencia de `vendor/bombercat-tools` **opcional** (degradación elegante, como
    `nfc`/`msr`): si no está, los paneles se ocultan.
- **Criterios de aceptación:** issue creado; cada PR es autocontenido, con tests verdes y descripción
  qué/por qué; la GUI arranca sin el submódulo vendor.
- **Complejidad:** Media-Alta. **Depende de Sesión 10.**

---

## 4. Criterios de buenas prácticas OpenSource (definición para este proyecto)

Un cambio cumple "buena práctica OSS" en este repo cuando satisface **todos** los aplicables:

- **Licencia y atribución:** conserva los avisos AGPL-3.0 y la autoría original (Glitchboi); si es
  derivado renombrado, lo declara en `NOTICE`/README.
- **Valor demostrable:** resuelve un problema real de usuario o de mantenimiento (registrado en la
  columna "Validación de valor" del progress log). Si no, no se ejecuta.
- **Aditivo y sin breaking changes innecesarios:** no rompe API/CLI/formatos de datos ni env vars de
  usuario sin alias de compatibilidad (≥1 versión) y nota en CHANGELOG.
- **Tests verdes:** `pytest tests/ -q` pasa; superficie nueva trae test (`fakecard`/`fakeserial`/
  headless GUI/TUI, según CONTRIBUTING).
- **Commits semánticos:** `feat:`/`fix:`/`docs:`/`refactor:`/`test:`…, mensaje que explica el
  **qué** y el **por qué**; `git mv` puro separado de la edición de contenido.
- **Documentación al día:** CLAUDE.md (arquitectura), CHANGELOG.md (cambios visibles), y docstrings
  en funciones públicas; textos de usuario en español (convención del repo).
- **Divergencia mínima con upstream:** no renombra estructuras del padre salvo decisión explícita de
  hard-fork (ADR-003).
- **Sin datos sensibles:** nunca PANs, tracks, capturas ni datos de cliente (SECURITY.md); revisar
  `git status` antes de commitear.

---

## 5. Preparación para upstream

Recomendaciones para que los cambios sean fáciles de revisar e integrar en
`Glitchboi-sudo/EMVy_Controller`:

- **Issue de propuesta primero.** Antes de invertir en el PR, abre un issue con el diseño (enlaza
  ADR-001/ADR-002) y deja que el mantenedor opine sobre el submódulo vendor.
- **PRs pequeños y secuenciales**, cada uno con tests verdes y una sola responsabilidad.
- **Nota para reviewers** en cada PR: resumen del qué/por qué, ADR enlazado, cómo probar (comando
  exacto), y qué queda fuera de alcance.
- **CHANGELOG por PR:** entrada en `CHANGELOG.md` (Keep a Changelog) describiendo el cambio visible.
- **Decisiones documentadas (ADR):** toda decisión de diseño no trivial va como ADR en el plan
  correspondiente, enlazada desde el PR.
- **Dependencia opcional:** la integración vendor debe degradar con elegancia si el submódulo no
  está, para no imponer una dependencia dura al padre.
- **DCO/sign-off** si upstream lo requiere; autoría de commits coherente.
- **Sin rebrand en el PR:** los PRs se hacen sobre el paquete `emvy` del padre; el nombre propio
  vive solo en tu fork/producto.

---

## 6. Blockers, dependencias y decisiones críticas

### 6.1 Grafo de dependencias entre sesiones
```
Sesión 1 (D-CORE) ──► Sesión 5 (destino rebrand) ──► Sesión 10 ──► Sesión 11
     │                                                    ▲
     └────────────────────────────────────────────────────┘
Sesión 2 (AGPL) ── independiente (ejecutar ya)
Sesión 3 (upstream remote) ── independiente ──► habilita Sesión 10
Sesiones 6,7,8,9 (firmware) ── independientes entre sí
```

### 6.2 Blockers conocidos
| ID | Blocker | Bloquea | Mitigación |
|---|---|---|---|
| B-1 | `D-CORE` sin resolver | Sesiones 5, 10, 11 | Ejecutar Sesión 1 primero; consultar a los actores. |
| B-2 | Sin remote `upstream` | Sesión 10 (rama limpia) | Sesión 3. |
| B-3 | Estado híbrido incoherente (rebrand a medias) | Coherencia documental | Sesión 2 + Sesión 5. |
| B-4 | Test de contrato vendor se salta si el venv no está | Sesión 8 (fiabilidad) | Aviso explícito en el skip. |

### 6.3 Decisiones críticas (registrar como ADR en §9)
- **D-CORE:** fork-contribución vs. hard-fork (Sesión 1 → ADR-003).
- **D-0:** nombre del producto si hay rebrand (reabierta en Sesión 1).
- **D-4:** rename del firmware `EMVyBomberCat` (diferida hasta D-CORE).

---

## 7. Progress log

> Actualiza **una fila por sesión** al terminarla. "Valor" = ¿agregó valor real? "OSS" = ¿cumple
> §4? Añade además el bloque detallado con el template de §10.

| # | Sesión | Estado | Cambios realizados | Valor (Sí/No + justificación) | OSS (Sí/No + notas) | Observaciones / Learnings |
|---|---|---|---|---|---|---|
| 1 | D-CORE: fork vs hard-fork | Completado | ADR-003 escrito (§9): **fork-contribución**; D-0 = mantener `cardsec` en brazo de producto | Sí — desbloquea Sesiones 5/10/11 y fija la estrategia de divergencia mínima | Sí — decisión trazada como ADR + progress log | `main` ya estaba limpio (`emvy`); el rebrand vive solo en `feature/refactor` mezclado con trabajo aditivo → Sesión 5 pasa de "completar" a "aislar" el rebrand. Notificación a actores (ElectronicCats/Glitchboi) pendiente para el usuario. |
| 2 | Cumplimiento AGPL y atribución | Completado | `NOTICE` creado (derivado de EMVy Controller/Glitchboi, AGPL-3.0, cadena de procedencia + fecha de mods) | Sí — cumple sección 5 AGPL y evita riesgo legal del estado híbrido | Sí — atribución intacta (29 refs), `authors=glitchboi` preservado | Coherencia de **nombre** (cardsec↔EMVy) se difiere a Sesión 5 (aislar rebrand) por ADR-003; `LICENSE` no traía línea de copyright del proyecto (vive en pyproject/README) → el `NOTICE` la hace explícita |
| 3 | Configurar `upstream` + sync | Completado | `git remote add upstream` + fetch OK; sección "Sincronización con upstream" en CONTRIBUTING; clone URL corregida a `ElectronicCats/Bombercat-GUI` | Sí — habilita traer mejoras del padre y medir divergencia (desbloquea Sesión 10) | Sí — flujo documentado, divergencia base registrada | Base de divergencia: upstream/main tiene 11 commits que no están en HEAD; HEAD tiene 36 propios; **origin/main está 11 detrás y 0 delante de upstream/main**; upstream ya en `v0.6.0-beta` |
| 4 | Validar valor Objetivo 1 | Completado | Diff de O1 (ADR-002) aislado contra `upstream/main` en la línea aditiva `emvy` (worktree): `gui/app.py`+`panels/tools.py`+`panels/fuzz.py` (~1356/892) | Sí — consistencia UX real, separable como PR propio | Sí — 0 refs cardsec en la línea aditiva; diff limpio sobre `emvy/` | El diff O1 sólo es limpio en la línea aditiva (`emvy`); sobre `feature/refactor` el rename lo contamina → confirma la necesidad de la rama de contribución |
| 5 | Destino del rebrand (Objetivo 2) | Completado | Rama `producto/cardsec` creada en HEAD (preserva rebrand); límite identificado (rebrand = 8 commits de tope `bfd7cb2..71dde03`; tip aditivo = `d130ae5`, `emvy` limpio); worktree de validación | Sí — aísla el rebrand sin perder el trabajo aditivo (fork-contribución, ADR-003) | Sí — no destructivo; `feature/refactor` está pusheada, force-push queda como decisión del usuario | Reescribir `feature/refactor` a `emvy` exige force-push (rama compartida) → NO ejecutado aquí; recomendación registrada abajo |
| 6 | Matriz de compatibilidad | Completado | Tabla en README (§ Compatibilidad de versiones) + enlace desde CLAUDE.md §12 | Sí — hace explícito qué `bombercat-tools`/`.uf2` soporta cada release | Sí — coincide con `PINNED_TAG` (v1.3.0) y `git submodule status` | Solo docs; §12 tenía versiones obsoletas (tools v1.1.0.0 / fw v1.2.0.0) → corregidas al pin real |
| 7 | Condición de salida firmware EMV | Completado | Nota de estado con **criterio de reactivación** explícito en CLAUDE.md §9 + entrada CHANGELOG | Sí — "temporal" pasa a tener condición de salida medible | Sí — cambio visible en CHANGELOG (Keep a Changelog) | Ruta documentación (no issue): no requiere GitHub; el criterio es (a) compila/flashea sin romper oficiales + (b) protocolo gated en Discovery-Contract |
| 8 | Robustez parsers + test contrato | Completado | Test de contrato por versión (`_CONTRACT_VENDOR_TAG`↔`PINNED_TAG`, siempre corre) + `test_version_matches_pinned_tag` + aviso visible cuando el venv del vendor no está listo (B-4) | Sí — la deriva del CLI/submódulo ya no pasa inadvertida | Sí — suite verde (31 en el módulo) | Los parsers YA estaban consolidados en `_table_rows` (parse_status/relay_*); el valor real era el test de contrato + el warning del skip mudo |
| 9 | Streaming §7.2 (opcional) | Completado | Decisión **no planeado** documentada en CLAUDE.md §12 (Alcance — streaming cancelable) | Sí — cierra el pendiente flotante sin gasto desproporcionado | Sí — decisión trazada; timeouts cubren el caso de uso | Vía Baja complejidad (descartar) en vez de implementar; reabrible como sesión propia si se necesita progreso en vivo |
| 10 | Rama `upstream-clean` | Pendiente | — | — | — | — |
| 11 | Trocear PRs + issue propuesta | Pendiente | — | — | — | — |

**Leyenda de Estado:** Pendiente · En Progreso · Completado · Bloqueado (indicar ID de blocker).

### Sesión 1 — Compuerta de decisión D-CORE — ✅ Completado (2026-09-18)
- **Cambios realizados:** `docs/Plan-Implementacion-Correcciones-OpenSource.md` — ADR-003 aceptado
  (§9), corrección de §1.2 (estado real del rebrand), progress log actualizado.
- **Validación de valor:** Sí — resuelve el blocker B-1; sin esta decisión no se puede actuar sobre
  Sesiones 5/10/11 ni cerrar la incoherencia documental.
- **Cumplimiento OSS (§4):** Sí — decisión documentada como ADR; sin cambios de código todavía.
- **Verificación:** hechos confirmados con `git remote -v`, `git ls-tree origin/main`,
  `git log origin/main..feature/refactor`, `git show origin/main:pyproject.toml`. No aplica pytest
  (sólo documentación).
- **Desviaciones / learnings:** el plan asumía el rebrand "a medias, sin commit final" y `main` en
  `emvy`; verificado que `main` **sí** está limpio en `emvy` (`name="emvycontroller"`) y que el
  rebrand **está commiteado** en `feature/refactor` mezclado con trabajo aditivo valioso. Esto
  **abarata** fork-contribución (la línea de contribución ya existe limpia) y reorienta la Sesión 5
  de "completar rebrand" a "aislar rebrand a rama de producto".
- **Pendiente para la siguiente sesión:** notificación formal a actores (ElectronicCats como dueño de
  `origin`; Glitchboi como autor del padre) queda como acción del usuario (enlace a issue/hilo).
  Continuar con Sesión 2 (AGPL/NOTICE) y Sesión 3 (remote `upstream`).

### Sesión 2 — Cumplimiento AGPL y atribución — ✅ Completado (2026-09-18)
- **Cambios realizados:** nuevo archivo `NOTICE` en la raíz declarando el trabajo derivado de
  `Glitchboi-sudo/EMVy_Controller` (© 2026 glitchboi), la cadena de procedencia
  (Glitchboi → ElectronicCats/Bombercat-GUI) y la indicación de modificación con fecha, bajo
  AGPL-3.0-or-later.
- **Validación de valor:** Sí — resuelve el riesgo legal del estado híbrido (§1.2, B-3) y cumple la
  sección 5 de la AGPL sobre avisos de autoría/modificación.
- **Cumplimiento OSS (§4):** Sí — atribución original conservada (`grep glitchboi` = 29 refs;
  `pyproject.authors` intacto); NOTICE presente.
- **Verificación:** `grep -rIn 'glitchboi\|Glitchboi' NOTICE pyproject.toml README.md CHANGELOG.md
  CONTRIBUTING.md` → 29 coincidencias; `git status` muestra `NOTICE` añadido. Sin cambios de código
  (no altera tests).
- **Desviaciones / learnings:** la coherencia plena de **nombre** entre los 5 documentos de
  gobernanza (cardsec vs EMVy Controller) NO se resuelve aquí: depende de la Sesión 5 (aislar el
  rebrand a rama de producto). Sesión 2 se limita a la **atribución**, que sí queda coherente e
  intacta. `LICENSE` no incluía una línea de copyright del proyecto; el `NOTICE` la hace explícita.
- **Pendiente para la siguiente sesión:** Sesión 3 (remote `upstream` + flujo de sync).

### Sesión 3 — Configurar `upstream` y flujo de sincronización — ✅ Completado (2026-09-18)
- **Cambios realizados:** remote `upstream` →
  `https://github.com/Glitchboi-sudo/EMVy_Controller.git` añadido y `git fetch upstream` OK;
  `CONTRIBUTING.md`: nueva sección "Sincronización con upstream" (flujo `fetch`+`merge`/`rebase`,
  política fork-contribución, enlace a NOTICE/ADR-003) y URL de `git clone` corregida a
  `ElectronicCats/Bombercat-GUI` (antes apuntaba a Glitchboi).
- **Validación de valor:** Sí — sin remote no se podía sincronizar ni medir la divergencia real; ahora
  ambas cosas son posibles (habilita Sesión 10).
- **Cumplimiento OSS (§4):** Sí — divergencia mínima documentada; atribución al padre reforzada.
- **Verificación:** `git remote -v` muestra `upstream`; `git fetch upstream` trajo `upstream/main` +
  tags `v0.5.0-beta`/`v0.6.0-beta`. **Línea base de divergencia:**
  `git log --oneline upstream/main ^HEAD | wc -l` = **11**; `HEAD ^upstream/main` = **36**;
  `origin/main` está **11 detrás / 0 delante** de `upstream/main`; merge-base = `53ec6ed`.
- **Desviaciones / learnings:** el padre (`upstream/main`) va **por delante** del fork
  (`origin/main`) en 11 commits y ya publicó `v0.6.0-beta` → la rama `upstream-clean` de la Sesión 10
  debe partir de `upstream/main` (no de `origin/main`) para no re-diverger. `upstream/main` usa
  `emvy/`, confirmando que la línea de contribución debe permanecer en `emvy`.
- **Pendiente para la siguiente sesión:** Fase A cerrada. Sigue Fase B — Sesión 4 (validar valor de
  Objetivo 1, aislar su diff `git diff upstream/main -- <gui>`) y Sesión 5 (aislar el rebrand a rama
  de producto). También queda, como acción del usuario, la notificación formal a los actores (§ADR-003).

### Sesión 4 — Validar el valor de Objetivo 1 — ✅ Completado (2026-09-18)
- **Cambios realizados:** ninguno de código. Análisis: diff de Objetivo 1 (ADR-002, aplanado de
  sub-tabs) aislado contra `upstream/main` en la línea aditiva `emvy` (worktree en `d130ae5`).
- **Validación de valor:** Sí — la reestructuración de Tabs es consistencia UX real y **separable**
  como PR propio (PR 3 de la Sesión 11).
- **Cumplimiento OSS (§4):** Sí — el diff es aditivo sobre `emvy/gui/`, sin renombrados (0 refs
  cardsec en esa línea).
- **Verificación:** `git diff --stat upstream/main d130ae5 -- emvy/gui/panels/tools.py
  emvy/gui/panels/fuzz.py emvy/gui/app.py` → 3 archivos, ~1356 ins / 892 del. Diff total de la GUI
  aditiva: 22 archivos, ~2815/1517. Superficie aditiva total `upstream/main..d130ae5`: 164 archivos.
- **Nota para reviewers (borrador PR O1):** "Aplana los sub-`QTabWidget` internos a Tabs de nivel
  superior (ADR-002): `ToolsPanel`→`FlagsPanel`/`IsoPanel`/`WritePanel` y `FuzzPanel`→
  `CardEditorPanel`/`EmulationPanel`/`EmvRecordPanel`/`MagfuzzPanel`. Motivo: descubribilidad. Probar:
  `QT_QPA_PLATFORM=offscreen pytest tests/test_gui.py -q`. Fuera de alcance: cualquier renombrado de
  paquete."
- **Desviaciones / learnings:** el diff de O1 sólo sale limpio en la línea `emvy`; sobre
  `feature/refactor` el rename `emvy→cardsec` lo contamina — refuerza que los PRs deben partir de la
  línea aditiva, no de la rama de producto.
- **Pendiente para la siguiente sesión:** el aislamiento efectivo del PR ocurre en Sesión 10.

### Sesión 5 — Destino del rebrand (fork-contribución) — ✅ Completado (2026-09-18)
- **Cambios realizados (no destructivos):** rama **`producto/cardsec`** creada en `HEAD` (71dde03),
  preservando íntegro el rebrand y el trabajo de producto. Worktree de validación en el tip aditivo
  `d130ae5` (paquete `emvy`, `name="emvycontroller"`).
- **Clasificación de los 36 commits `upstream/main..HEAD`:**
  - **Rebrand/branding/docs (8, producto-only):** `bfd7cb2` (git mv paquete/firmware/packaging),
    `3956fad` (refs internas), `64f07f6` (tests namespace), `5baa50b` (entry point/config test),
    `ee02230` (config), `40ae397` (workflow), `13a210f` (título ventana), `71dde03` (CLAUDE.md).
  - **Aditivo/infra contribuible (28, `d130ae5`→`a26b0d3`):** integración BomberCat (submódulo
    bombercat-tools, paneles firmware ADR-001: Device/Tags/Readers/Magspoof/Mifare/Relay, flasheo),
    Objetivo 1 (ADR-002), CI/pre-commit.
  - **Límite:** el rebrand está **contiguo en el tope**; el último commit de código aditivo es
    `d130ae5`.
- **Validación de valor:** Sí — aísla el rebrand a rama de producto sin perder el trabajo aditivo,
  cumpliendo fork-contribución (ADR-003).
- **Cumplimiento OSS (§4):** Sí — divergencia mínima en la línea de contribución; sin operaciones
  destructivas.
- **Verificación:** `git branch producto/cardsec HEAD` OK; `git diff upstream/main d130ae5
  --name-only | grep -c cardsec` = **0**; suite en `emvy` (worktree, `PYTHONPATH` + `.venv` principal,
  `QT_QPA_PLATFORM=offscreen`) → **241 passed, 29 skipped** (exit 0). Los 29 skips (vs. 2 en HEAD)
  son tests de `bombercat-tools` que se saltan sin el venv del vendor listo — el riesgo que endurece
  la Sesión 8.
- **Desviaciones / learnings:** `feature/refactor` **está pusheada** (`HEAD == origin/feature/refactor`),
  por lo que devolverla a `emvy` (reset a `d130ae5`) requiere **force-push** a una rama compartida —
  acción externa/irreversible que **queda a decisión del usuario**, no ejecutada aquí.
- **Recomendación de estrategia de ramas (para el usuario):**
  1. `producto/cardsec` (ya creada) → línea de producto con rebrand; aquí van XDG-migration (D-2),
     alias `EMVY_*`, NOTICE y branding.
  2. Línea de contribución: en Sesión 10 se crea `upstream-clean` desde `upstream/main` y se
     reaplican los 28 commits aditivos (`a26b0d3..d130ae5`) **sin** rebrand.
  3. Opcional (tu decisión): resetear `feature/refactor` a `d130ae5` y `git push --force-with-lease`
     para que la rama de trabajo compartida vuelva a `emvy`; coordínalo con Electronic Cats antes.
- **Pendiente para la siguiente sesión:** Fase C (Sesiones 6–9, firmware, independientes) o Fase D
  (Sesión 10, rama `upstream-clean`). Confirmar/ejecutar el force-push de `feature/refactor` si se opta.

### Sesión 6 — Matriz de compatibilidad de versiones — ✅ Completado (2026-09-18)
- **Cambios realizados:** `README.md` — nueva sección **"Compatibilidad de versiones"** con la matriz
  `release de la app ↔ bombercat-tools (PINNED_TAG) ↔ firmwares .uf2 soportados ↔ repo de firmware`.
  `CLAUDE.md` §12 — callout que enlaza la matriz y corrige las versiones obsoletas del texto (decía
  tools `v1.1.0.0` y fw release `v1.2.0.0`) por el pin real `v1.3.0`.
- **Validación de valor:** Sí — la comunidad ya sabe qué versión de `bombercat-tools` y qué imágenes
  `.uf2` soporta cada release, antes implícito solo en `PINNED_TAG`.
- **Cumplimiento OSS (§4):** Sí — documentación al día y coherente; sin cambios de código.
- **Verificación:** `git submodule status` → `v1.3.0`; `PINNED_TAG = "v1.3.0"`;
  `.gitmodules` apunta a `ElectronicCats/bombercat-tools` → los tres coinciden con la tabla.
- **Desviaciones / learnings:** las imágenes `.uf2` NO están fijadas por nosotros (se bajan de la
  release `latest` de `bombercat-firmware` vía `ReleaseCache`); la matriz lo hace explícito.
- **Pendiente para la siguiente sesión:** —

### Sesión 7 — Condición de salida del firmware EMV — ✅ Completado (2026-09-18)
- **Cambios realizados:** `CLAUDE.md` §9 — callout de estado que declara el firmware EMV propio
  **temporalmente inactivo** con **condición de reactivación explícita** (compila/flashea sin romper
  las imágenes oficiales **y** protocolo declarado como capacidad gated en el Discovery-Contract).
  `CHANGELOG.md` — sección `[Unreleased]` con la entrada "Cambiado".
- **Validación de valor:** Sí — "temporal" deja de ser indefinido; hay criterio medible de salida.
- **Cumplimiento OSS (§4):** Sí — cambio visible registrado en CHANGELOG (Keep a Changelog).
- **Verificación:** revisión de texto; sin superficie de ejecución (no altera tests).
- **Desviaciones / learnings:** se optó por la vía **documentación/deprecación** (no issue GitHub),
  que no requiere credenciales y deja el criterio en la wiki viva (`CLAUDE.md`).
- **Pendiente para la siguiente sesión:** —

### Sesión 8 — Robustez de parsers + test de contrato por versión — ✅ Completado (2026-09-18)
- **Cambios realizados:** `tests/test_bombercat_tools.py` — (1) `_CONTRACT_VENDOR_TAG = "v1.3.0"` +
  `test_canned_samples_match_pinned_vendor_tag` (siempre corre, sin venv): ancla las tablas rich
  canned a la versión del vendor y falla si `PINNED_TAG` diverge; (2) `test_version_matches_pinned_tag`
  (gated a venv): el gitlink del submódulo debe estar exactamente en `PINNED_TAG`; (3) **aviso
  visible** (`warnings.warn`) cuando el vendor está pero su venv no, para que el skip de los tests de
  contrato **no oculte deriva** (B-4); condiciones `skipif` unificadas en `_VENV_READY`.
- **Validación de valor:** Sí — la deriva del CLI del vendor o del submódulo frente al pin ya no pasa
  inadvertida; un bump de `PINNED_TAG` obliga a re-verificar los parsers.
- **Cumplimiento OSS (§4):** Sí — superficie nueva con test; suite verde.
- **Verificación:** `.venv/bin/python -m pytest tests/test_bombercat_tools.py -q` → **31 passed**
  (29 previos + 2 de contrato); `bt.version()` = `"1.3.0"` == `PINNED_TAG.lstrip("v")`.
- **Desviaciones / learnings:** los parsers **ya** estaban consolidados en un único punto
  (`_table_rows` reusado por `parse_status`/`parse_relay_config`/`parse_relay_status`); la consolidación
  que pedía la Sesión 8 estaba hecha, así que el valor entregado fue el **test de contrato** + el
  **warning del skip mudo** (el riesgo B-4).
- **Pendiente para la siguiente sesión:** —

### Sesión 9 — Streaming §7.2 — ✅ Completado (2026-09-18, "no planeado")
- **Cambios realizados:** `CLAUDE.md` §12 — callout **"Alcance — streaming cancelable (decisión: no
  planeado)"**: los comandos largos se acotan por `timeout` (nunca streaming por líneas cancelable);
  se declara fuera de alcance a propósito, reabrible como sesión propia.
- **Validación de valor:** Sí — cierra el pendiente flotante §7.2 sin invertir en orquestación
  (PIPE+progress+cancelación) de valor no proporcional al caso de uso.
- **Cumplimiento OSS (§4):** Sí — decisión trazada en la wiki viva.
- **Verificación:** revisión de texto; sin cambios de código.
- **Desviaciones / learnings:** vía Baja complejidad (descartar) de las dos que ofrecía el plan.
- **Pendiente para la siguiente sesión:** Fase C cerrada. Sigue **Fase D** — Sesión 10 (rama
  `upstream-clean` desde `upstream/main`, reaplicar los 28 commits aditivos sin rebrand) y Sesión 11
  (trocear PRs + issue de propuesta + dependencia vendor opcional). Queda además, como acción del
  usuario, la notificación formal a los actores (§ADR-003) y la decisión del force-push de
  `feature/refactor` (Sesión 5).

---

## 8. Registro de blockers activos

> Añade una fila cuando surja un blocker; muévelo a "Resuelto" con fecha cuando se cierre.

| ID | Descripción | Sesión afectada | Estado | Fecha alta | Resolución / fecha |
|---|---|---|---|---|---|
| B-1 | `D-CORE` sin resolver | 5, 10, 11 | Resuelto | 2026-09-18 | ADR-003 = fork-contribución (2026-09-18) |
| B-2 | Sin remote `upstream` | 10 | Resuelto | 2026-09-18 | `git remote add upstream` + fetch (2026-09-18) |
| B-3 | Estado híbrido incoherente (rebrand a medias) | Coherencia documental | Parcial | 2026-09-18 | Atribución resuelta (NOTICE, Sesión 2); coherencia de **nombre** pendiente de Sesión 5 |
| B-4 | Test de contrato vendor se salta si el venv no está (skip mudo) | 8 | Resuelto | 2026-09-18 | `warnings.warn` visible al saltar + test de contrato `_CONTRACT_VENDOR_TAG` que corre sin venv (Sesión 8, 2026-09-18) |

---

## 9. Decisiones (ADR de este plan)

> Registra aquí cada decisión crítica tomada durante la ejecución. Formato ADR breve.

### ADR-003 — Naturaleza del proyecto: fork-contribución vs. hard-fork
- **Estado:** **Aceptada** (2026-09-18, Sesión 1).
- **Contexto:** rebrand y contribución upstream son incompatibles (§1.3). Estado verificado en árbol
  al decidir: `origin/main` está **limpio** (paquete `emvy/`, `pyproject.name = "emvycontroller"`);
  el rebrand `emvy → cardsec` vive **solo en `feature/refactor`** (5 commits) **mezclado** con
  trabajo aditivo valioso (refactor de Tabs O1 e integración BomberCat: Mifare/Relay/NFCGate/paneles
  de firmware). No hay remote `upstream`, no existe `NOTICE`.
- **Decisión:** **(A) Fork-contribución.** Se prioriza aportar upstream a
  `Glitchboi-sudo/EMVy_Controller`. La **línea principal** (`main` y la rama de trabajo destinada a
  PRs) permanece **sin renombrados**, con el paquete `emvy/`. El rebrand se **aísla** en una rama de
  producto aparte. **D-0:** si/donde exista rebrand, el nombre del producto es **`cardsec`**.
- **Justificación:** `main` ya está limpio en `emvy`, así que fork-contribución es de bajo coste en
  la línea principal y preserva la mergeabilidad de la integración BomberCat (el cambio de mayor
  valor, §2). El rebrand aporta valor sólo al producto propio, no al upstream; aislarlo evita hacer
  inmergeable el trabajo aditivo. Mantener `cardsec` como nombre del brazo de producto respeta lo ya
  ejecutado en `feature/refactor` sin re-renombrar.
- **Consecuencias:**
  - **§2 (auditoría):** el rebrand queda "Negativo para upstream / conservar sólo en rama de
    producto". La migración XDG (D-2) y los alias `EMVY_*` sólo aplican en el brazo de producto.
  - **Sesión 5** deja de ser "completar el rebrand": pasa a **aislar** el rebrand de
    `feature/refactor` a una rama `producto/cardsec` y devolver la línea de contribución a `emvy`.
  - **Sesión 2 (AGPL/NOTICE)** se ejecuta igualmente (obligatoria en ambos caminos).
  - **Fase D (Sesiones 10–11)** queda habilitada: rama `upstream-clean` desde `upstream/main` con
    sólo los cambios aditivos sobre `emvy/`.
  - **D-4** (rename del firmware) se mantiene **diferido**: no se renombra en la línea de
    contribución (el handshake serie es invariante, ver Discovery-Contract).

---

## 10. Template para nuevas sesiones

> Copia este bloque al añadir una sesión nueva, y su fila correspondiente al Progress log (§7).

```markdown
#### Sesión N — <título>
- **Descripción:** <qué y por qué, en 1–2 frases>
- **Objetivos:** <lista de objetivos específicos y medibles>
- **Cambios propuestos:** <referencia a doc/§ exacta de los planes adjuntos + archivos afectados>
- **Criterios de aceptación:** <qué hace válido el cambio: tests, coherencia, verificación funcional>
- **Complejidad:** <Baja/Media/Alta> — **Depende de:** <sesiones previas / ninguno>
```

**Bloque de cierre (añadir al Progress log detallado al terminar la sesión):**

```markdown
### Sesión N — <título> — <✅ Completado / 🚧 En progreso / ⛔ Bloqueado (B-x)> (<fecha>)
- **Cambios realizados:** <archivos + resumen>
- **Validación de valor:** <Sí/No> — <justificación breve>
- **Cumplimiento OSS (§4):** <Sí/No> — <notas: licencia, tests, commits, docs>
- **Verificación:** <comando(s) + resultado, p.ej. `pytest tests/ -q` → N passed>
- **Desviaciones / learnings:** <qué se descubrió respecto al plan; actualizar §2 si cambió el valor>
- **Pendiente para la siguiente sesión:** <handoff explícito>
```

---

## 11. Referencias

- Análisis de buenas prácticas OSS (origen de estas correcciones): conversación asociada / informe.
- Plan de reestructuración y rebrand: `docs/Plan-Reestructuracion-EMVY-y-Rebrand.md`.
- Plan de integración de firmwares: `docs/Plan-Integracion-Firmwares-BomberCat.md`.
- Contrato de descubrimiento (handshake serie, invariante al rebrand):
  `docs/BomberCatControl-Discovery-Contract.md`.
- Licencia: `LICENSE` (AGPL-3.0-or-later, © 2026 glitchboi).
- Gobernanza: `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `.github/`.
- Wiki viva / arquitectura: `CLAUDE.md`.
