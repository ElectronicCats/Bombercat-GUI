# Contribuir a EMVy Controller

¡Gracias por tu interés! Esta guía resume el flujo de trabajo y las convenciones. La referencia
completa de arquitectura está en **[`CLAUDE.md`](CLAUDE.md)** (la wiki del proyecto).

## Antes de empezar

- El proyecto está en **BETA**: la API interna puede cambiar. Coordina cambios grandes en un issue
  antes de invertir mucho tiempo.
- **Nunca** subas datos de cliente, capturas de tarjeta, PANs, tracks ni claves. Están excluidos por
  `.gitignore`; revisa tu `git status` antes de commitear. Ver [`SECURITY.md`](SECURITY.md).

## Configurar el entorno

```sh
git clone https://github.com/Glitchboi-sudo/EMVy_Controller.git
cd EMVy_Controller

uv venv .venv
uv pip install --python .venv -e '.[dev,tui,gui]'
```

Dependencias del sistema para `pyscard`: ver [`docs/INSTALACION.md`](docs/INSTALACION.md).

## Ejecutar las pruebas

```sh
.venv/bin/python -m pytest tests/ -q     # suite offline, sin hardware (238 tests)
```

Toda la suite corre **sin hardware** gracias a la tarjeta simulada (`tests/fakecard.py`) y al serial
falso (`tests/fakeserial.py`). **Todo PR debe dejar la suite en verde.**

## Convenciones de código (importante)

Del `CLAUDE.md §6`:

- **Funcional primero**: `emvy/core/` es **puro** — sin IO, sin estado global, sin `print`/color. Las
  funciones reciben sus dependencias como argumentos (p.ej. `send: Transceiver`, `profile`, rutas).
- **Efectos en los bordes**: el IO de hardware vive en `emvy/readers/`; el de disco en
  `emvy/project/` y `emvy/session/`; la presentación (color/Textual/Qt) en `term.py`/`tui/`/`gui/`.
- **Inmutabilidad**: los modelos de datos son `@dataclass(frozen=True)`. Para "modificar", usa
  `dataclasses.replace` y **devuelve** una copia; no mutes en sitio.
- **Reutiliza**: antes de escribir, busca en `core.hexutil`, `core.tlv`, `core.apdu`, `env`. P.ej.
  serializa TLV con `tlv.encode`, no reconstruyas bytes a mano.
- **Estilo**: PEP 8, type hints, `snake_case`/`PascalCase`/`UPPER_CASE`, f-strings, `pathlib`,
  docstrings en funciones públicas.
- **Idioma**: comentarios y textos de usuario en **español** (consistencia con el resto del código).

### Al cambiar algo con superficie de ejecución

- Núcleo/flujo EMV → añade/ajusta un test con `tests/fakecard.py`.
- Serie/BomberCat → usa `tests/fakeserial.py` (emula el firmware).
- TUI → prueba de humo headless con `App.run_test()` (Textual Pilot).
- GUI → verificable headless con `QT_QPA_PLATFORM=offscreen` + `QWidget.grab()`.
- **Actualiza `CLAUDE.md`** cuando cambie la arquitectura, y `CHANGELOG.md` para cambios visibles.

## Flujo de Pull Request

1. Crea una rama descriptiva (`feat/...`, `fix/...`, `docs/...`).
2. Haz commits pequeños y con mensajes claros (en español o inglés, consistentes).
3. Asegúrate de que `pytest` pasa y de que no incluyes datos sensibles.
4. Abre el PR contra `main` describiendo el **qué** y el **por qué**.

## Reportar issues

Usa las plantillas de issue. Para reportes de bug incluye: versión (`emvy.__version__`), distro, cómo
lo instalaste (AppImage/fuente), pasos de reproducción y salida relevante — **sin datos de tarjeta**.
