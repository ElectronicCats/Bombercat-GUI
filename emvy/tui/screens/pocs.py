"""Panel de PoCs con un mini-IDE tipo VS Code: barra de herramientas (ejecución
+ acciones de archivo), un explorador lateral de `<proyecto>/pocs/*.py`, el editor
Python al centro y un panel de salida (resultados) abajo.

Seleccionar un archivo/PoC en el explorador **abre su código** en el editor.
"""
from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
    TextArea,
)

from ... import poc as pocmod
from ...poc.scaffold import scaffold_poc
from ...poc.templates import list_templates as _templates
from ...project import store

_CARD_SOURCES = [
    ("Sin tarjeta", "none"),
    ("Sesión (última captura)", "session"),
    ("Captura guardada", "saved"),
    ("Lector en vivo", "live"),
]


class PocScreen(Vertical):
    DEFAULT_CSS = """
    PocScreen #poc_toolbar { height: auto; }
    PocScreen #poc_toolbar Horizontal { height: auto; padding: 0 0 1 0; }
    PocScreen #poc_toolbar Select { width: 22; margin: 0 1 0 0; }
    PocScreen #poc_toolbar Checkbox { margin: 0 1 0 0; }
    PocScreen #poc_toolbar Button { margin: 0 1 0 0; }
    PocScreen #poc_newid { width: 20; margin: 0 1 0 0; }

    PocScreen #poc_body { height: 1fr; }
    PocScreen #poc_sidebar {
        width: 34; background: $panel; border-right: heavy $primary; padding: 0 1;
    }
    PocScreen .section { text-style: bold; color: $accent; }
    PocScreen #poc_files { height: 2fr; background: $panel; border: none; }
    PocScreen #poc_ref { height: 1fr; color: $text-muted; padding: 1 0 0 0; }
    PocScreen #poc_main { width: 1fr; padding: 0 0 0 1; }
    PocScreen #poc_editor { height: 1fr; border: round $primary; }
    PocScreen #poc_output { height: 9; }
    PocScreen #poc_log { height: 1fr; border: round $primary; }
    """

    def compose(self):
        yield Label("PoCs — IDE", classes="title")
        yield Label("", id="poc_hint", classes="hint")

        with Vertical(id="poc_toolbar"):
            with Horizontal():
                yield Select(_CARD_SOURCES, value="session", allow_blank=False, id="poc_cardsrc")
                yield Select([], prompt="captura…", allow_blank=True, id="poc_capfile")
                yield Checkbox("dry-run", value=True, id="poc_dry")
                yield Checkbox("allow-write", id="poc_write")
                yield Button("▶ Ejecutar", id="poc_run", variant="success")
            with Horizontal():
                yield Input(placeholder="id del nuevo PoC", id="poc_newid")
                yield Select([(t, t) for t in _templates()], prompt="plantilla…",
                             allow_blank=True, id="poc_template")
                yield Button("Nuevo", id="poc_new", variant="primary")
                yield Button("Guardar", id="poc_save", variant="success")
                yield Button("Eliminar", id="poc_del", variant="error")
                yield Button("Recargar", id="poc_reload")

        with Horizontal(id="poc_body"):
            with Vertical(id="poc_sidebar"):
                yield Label("EXPLORER", classes="section")
                yield ListView(id="poc_files")
                yield Static("", id="poc_ref")
            with Vertical(id="poc_main"):
                yield self._make_editor()

        with Vertical(id="poc_output"):
            yield Label("OUTPUT", classes="section")
            yield RichLog(id="poc_log", markup=True, wrap=True)

    @staticmethod
    def _make_editor():
        try:
            ed = TextArea.code_editor("", language="python", id="poc_editor")
        except Exception:
            ed = TextArea("", id="poc_editor")
        return ed

    def on_mount(self):
        self._files: list[str] = []
        self._file_pocs: dict[str, list[str]] = {}
        self._open_file: str | None = None
        self._run_target: str | None = None
        self._loading = False
        self.reload()

    # -- recarga: pocs + archivos + capturas + referencia ------------------
    def reload(self):
        proj = store.active_project()
        hint = self.query_one("#poc_hint", Label)
        lv = self.query_one("#poc_files", ListView)
        self._loading = True
        lv.clear()
        self._files = []
        self._file_pocs = {}

        if not proj:
            hint.update("[yellow]No hay proyecto activo (pestaña Proyectos).[/]")
            self._set_options("#poc_capfile", [])
            self.query_one("#poc_ref", Static).update("")
            self._loading = False
            return

        pocmod.clear()
        loaded, errors = pocmod.load_plugins(proj)
        for pid in loaded:
            self._file_pocs.setdefault(pocmod.source_file(pid) or "?", []).append(pid)

        files = sorted(f.name for f in proj.pocs_dir.glob("*.py")) if proj.pocs_dir.exists() else []
        for fname in files:
            self._files.append(fname)
            lv.append(ListItem(Label(self._file_label(fname))))
        self._loading = False

        n = sum(len(v) for v in self._file_pocs.values())
        msg = f"Proyecto [b]{proj.name}[/] — {len(files)} archivo(s), {n} PoC(s)"
        if errors:
            msg += f"  [red]({len(errors)} con error de carga)[/]"
        hint.update(msg)

        self._set_options("#poc_capfile", [(c.name, c.name) for c in store.list_captures(proj)])
        self.query_one("#poc_ref", Static).update(self._reference(proj))

    def _file_label(self, fname: str) -> str:
        pocs = self._file_pocs.get(fname, [])
        if not pocs:
            return f"📄 {fname}  [red](sin PoC)[/]"
        pid = pocs[0]
        p = pocmod.get(pid)
        sev = str(p.meta.severity) if p else "?"
        extra = f" +{len(pocs) - 1}" if len(pocs) > 1 else ""
        return f"📄 {fname}\n   [dim]{pid} [{sev}]{extra}[/]"

    def _reference(self, proj) -> str:
        try:
            names = [v.name for v in store.load_project_variables(proj)]
        except Exception:
            names = []
        dev = getattr(self.app, "reader_device", None)
        reader = dev.name if dev else "ninguno"
        varlist = ", ".join(names[:16]) + (" …" if len(names) > 16 else "") or "(ninguna)"
        return ("[b]ctx[/]: var/require · card · http() · save_evidence · finding/result\n"
                f"[b]vars[/]: {varlist}\n[b]lector[/]: {reader}")

    def _set_options(self, sel_id: str, options):
        self.query_one(sel_id, Select).set_options(options)

    # -- explorador: abrir al seleccionar/navegar --------------------------
    @on(ListView.Highlighted, "#poc_files")
    @on(ListView.Selected, "#poc_files")
    def _pick(self, event):
        if self._loading:
            return
        idx = event.list_view.index
        if idx is None or not (0 <= idx < len(self._files)):
            return
        self._open(self._files[idx])

    def _open(self, filename: str):
        proj = store.active_project()
        if not proj:
            return
        try:
            content = (proj.pocs_dir / filename).read_text()
        except Exception as e:
            self.app.notify(f"No se pudo abrir: {e}", severity="error")
            return
        self.query_one("#poc_editor", TextArea).text = content
        self._open_file = filename
        pocs = self._file_pocs.get(filename, [])
        self._run_target = pocs[0] if pocs else None
        tgt = f" · ejecutará [b]{self._run_target}[/]" if self._run_target else " · [red]sin PoC cargable[/]"
        self.query_one("#poc_hint", Label).update(f"Editando [b]{filename}[/]{tgt}")

    # -- ejecutar -----------------------------------------------------------
    @on(Button.Pressed, "#poc_run")
    def _run(self):
        if not self._run_target:
            self.app.notify("Abre en el explorador un archivo con un PoC cargable.",
                            severity="warning")
            return
        source = self.query_one("#poc_cardsrc", Select).value
        capfile = self.query_one("#poc_capfile", Select).value
        if source == "saved" and (capfile is Select.BLANK or not capfile):
            self.app.notify("Elige una captura guardada.", severity="warning")
            return
        self.app.run_poc_ui(
            self._run_target,
            card_source=source,
            capture_name=(capfile if source == "saved" else None),
            dry_run=self.query_one("#poc_dry", Checkbox).value,
            allow_write=self.query_one("#poc_write", Checkbox).value,
        )

    @on(Button.Pressed, "#poc_reload")
    def _reload_btn(self):
        self.reload()

    # -- IDE: crear / guardar / eliminar -----------------------------------
    def _proj(self):
        proj = store.active_project()
        if not proj:
            self.app.notify("No hay proyecto activo (pestaña Proyectos).", severity="warning")
        return proj

    @on(Button.Pressed, "#poc_new")
    def _new(self):
        proj = self._proj()
        if not proj:
            return
        pid = self.query_one("#poc_newid", Input).value.strip()
        if not pid:
            self.app.notify("Indica un id para el nuevo PoC.", severity="warning")
            return
        from textual.widgets import Select
        val = self.query_one("#poc_template", Select).value
        tmpl = val if isinstance(val, str) else None    # el sentinela "sin selección" no es str
        try:
            path = scaffold_poc(proj.pocs_dir, pid, template=tmpl)
        except FileExistsError:
            self.app.notify(f"Ya existe un archivo para {pid!r}.", severity="error")
            return
        except KeyError as e:
            self.app.notify(str(e), severity="error")
            return
        self.query_one("#poc_newid", Input).value = ""
        self.reload()
        self._open(path.name)
        self.app.notify(f"PoC creado: {path.name}")

    @on(Button.Pressed, "#poc_save")
    def _save(self):
        proj = self._proj()
        if not proj:
            return
        if not self._open_file:
            self.app.notify("No hay archivo abierto (usa Nuevo o selecciona uno).",
                            severity="warning")
            return
        try:
            (proj.pocs_dir / self._open_file).write_text(
                self.query_one("#poc_editor", TextArea).text)
        except Exception as e:
            self.app.notify(f"No se pudo guardar: {e}", severity="error")
            return
        opened = self._open_file
        self.reload()
        self._open(opened)
        self.app.notify(f"Guardado {opened}. Recargado.")

    @on(Button.Pressed, "#poc_del")
    def _delete(self):
        proj = self._proj()
        if not proj:
            return
        if not self._open_file:
            self.app.notify("Abre el archivo que quieres eliminar.", severity="warning")
            return
        target = self._open_file
        try:
            (proj.pocs_dir / target).unlink()
        except Exception as e:
            self.app.notify(f"No se pudo eliminar: {e}", severity="error")
            return
        self._open_file = None
        self._run_target = None
        self.query_one("#poc_editor", TextArea).text = ""
        self.reload()
        self.app.notify(f"Eliminado {target}.", severity="warning")

    # -- llamado por la app tras ejecutar ----------------------------------
    def log_result(self, meta, result, run_dir) -> None:
        log = self.query_one("#poc_log", RichLog)
        color = {"vulnerable": "red", "error": "red", "passed": "green",
                 "not_vulnerable": "green"}.get(str(result.status), "cyan")
        log.write(f"[b {color}][{result.status}][/] [b]{meta.title}[/] ({meta.id})")
        if result.summary:
            log.write(f"  {result.summary}")
        for f in result.findings:
            log.write(f"  · [yellow][{f.severity}][/] {f.title}"
                      + (f" — {f.detail}" if f.detail else ""))
        if result.error:
            log.write(f"  [red]error: {result.error}[/]")
        log.write(f"  [dim]run: {run_dir}[/]")
