"""Panel de proyectos: crear, activar y eliminar espacios de trabajo."""

from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static

from ...project import store
from ..widgets.copyable import CopyableDataTable


class ProjectsScreen(Vertical):
    def compose(self):
        yield Static("Proyectos", classes="title")
        yield Static(
            "Espacios de trabajo (XDG o en ruta/engagements). Marca ● = activo.",
            classes="subtitle",
        )
        yield CopyableDataTable(id="proj_table")
        with Horizontal(classes="row"):
            yield Input(placeholder="nombre del proyecto", id="proj_name")
            yield Input(placeholder="descripción (opcional)", id="proj_desc")
        with Horizontal(classes="row"):
            yield Input(
                placeholder="ruta (opcional; vacío = ~/.local/share/emvy/projects)",
                id="proj_path",
            )
            yield Button("Elegir engagements/", id="proj_path_eng")
        with Horizontal(classes="row"):
            yield Button("Crear + activar", id="proj_new", variant="success")
            yield Button("Activar selección", id="proj_use", variant="primary")
            yield Button("Eliminar selección", id="proj_del", variant="error")

    def on_mount(self):
        t = self.query_one("#proj_table", DataTable)
        t.add_columns("", "nombre", "creado", "descripción")
        t.cursor_type = "row"
        self._rows: list[str] = []
        self.reload()

    def reload(self):
        t = self.query_one("#proj_table", DataTable)
        t.clear()
        active = store.active_project()
        active_rp = active.path.resolve() if active else None
        self._rows = []

        def _mark(p):
            return "●" if active_rp and p.path.resolve() == active_rp else ""

        for p in store.list_projects():
            t.add_row(_mark(p), p.name, p.created, p.description)
            self._rows.append((p.name, None))  # XDG: activar por nombre
        for p in store.list_path_projects():
            desc = f"{p.description}  ·  {p.path}" if p.description else str(p.path)
            t.add_row(_mark(p), p.name, "engagement", desc)
            self._rows.append((p.name, p.path))  # ruta: activar por path

    def _selected(self):
        t = self.query_one("#proj_table", DataTable)
        if not self._rows:
            return None
        idx = t.cursor_row or 0
        return self._rows[idx] if idx < len(self._rows) else None

    @on(Button.Pressed, "#proj_path_eng")
    def _path_eng(self):
        """Rellena la ruta con engagements/<nombre> (proyecto versionado en el repo)."""
        name = self.query_one("#proj_name", Input).value.strip() or "cliente"
        from ... import config

        self.query_one("#proj_path", Input).value = str(
            config.engagements_dirs()[0] / name
        )

    @on(Button.Pressed, "#proj_new")
    def _new(self):
        name = self.query_one("#proj_name", Input).value.strip()
        desc = self.query_one("#proj_desc", Input).value.strip()
        path = self.query_one("#proj_path", Input).value.strip()
        if not name and not path:
            self.app.notify("Indica un nombre (o una ruta).", severity="warning")
            return
        try:
            if path:  # proyecto en ruta (elige dónde)
                p = store.create_project_at(path, name=name or None, description=desc)
                store.set_active_path(p.path)
            else:  # proyecto XDG por defecto
                store.create_project(name, description=desc)
                store.set_active(name)
        except Exception as e:
            self.app.notify(str(e), severity="error")
            return
        for wid in ("#proj_name", "#proj_desc", "#proj_path"):
            self.query_one(wid, Input).value = ""
        self.app.refresh_ui()
        self.app.notify(f"Proyecto creado y activado: {store.active_label()}")

    @on(Button.Pressed, "#proj_use")
    def _use(self):
        sel = self._selected()
        if not sel:
            self.app.notify("Selecciona un proyecto.", severity="warning")
            return
        name, path = sel
        if path is not None:
            store.set_active_path(path)
        else:
            store.set_active(name)
        self.app.refresh_ui()
        self.app.notify(f"Proyecto activo: {store.active_label()}")

    @on(Button.Pressed, "#proj_del")
    def _del(self):
        sel = self._selected()
        if not sel:
            self.app.notify("Selecciona un proyecto.", severity="warning")
            return
        name, path = sel
        if path is not None:
            self.app.notify(
                "Los engagements en ruta no se borran desde aquí "
                "(viven en el repo).",
                severity="warning",
            )
            return
        try:
            store.delete_project(name)
        except Exception as e:
            self.app.notify(str(e), severity="error")
            return
        self.app.refresh_ui()
        self.app.notify(f"Proyecto {name!r} eliminado.", severity="warning")
