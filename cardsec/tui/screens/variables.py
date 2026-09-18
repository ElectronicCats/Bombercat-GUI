"""Panel de variables de entorno del proyecto activo (perfil terminal + libres)."""

from __future__ import annotations

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Input, Label, Select, Static

from ...project import env as envmod
from ...project import profiles as profilesmod
from ...project import store
from ..widgets.copyable import CopyableDataTable


class VariablesScreen(Vertical):
    def compose(self):
        yield Static("Variables de entorno", classes="title")
        yield Static(
            "Perfil de terminal EMV (mapeado a tags) + variables libres "
            "del proyecto activo. Aplica un perfil preconfigurado abajo.",
            classes="subtitle",
        )
        yield Label("", id="var_hint", classes="hint")
        yield CopyableDataTable(id="var_table")
        with Horizontal(classes="row"):
            yield Input(
                placeholder="nombre / alias / tag (p.ej. amount, 9F02)", id="var_name"
            )
            yield Input(
                placeholder="valor (texto para an/ans, hex para el resto)",
                id="var_value",
            )
        with Horizontal(classes="row"):
            yield Checkbox("variable libre (no terminal)", id="var_user")
            yield Button("Guardar", id="var_set", variant="success")
            yield Button("Borrar selección", id="var_del", variant="error")
            yield Button("Recargar", id="var_reload")
        with Horizontal(classes="row"):
            yield Select(
                [(p.title, p.id) for p in profilesmod.list_profiles()],
                prompt="perfil de terminal preconfigurado…",
                allow_blank=True,
                id="var_profile",
            )
            yield Button("Aplicar perfil", id="var_apply_profile", variant="primary")
        yield Label("", id="var_profile_desc", classes="hint")

    def on_mount(self):
        t = self.query_one("#var_table", DataTable)
        t.add_columns("tag", "nombre", "valor", "tipo")
        t.cursor_type = "row"
        self._rows: list[str] = []
        self.reload()

    def reload(self):
        t = self.query_one("#var_table", DataTable)
        t.clear()
        self._rows = []
        proj = store.active_project()
        hint = self.query_one("#var_hint", Label)
        if not proj:
            hint.update(
                "[yellow]No hay proyecto activo. Créalo/actívalo en la pestaña Proyectos.[/]"
            )
            return
        hint.update(f"Proyecto activo: [b]{proj.name}[/]")
        variables = store.load_project_variables(proj)
        for v in sorted(
            variables, key=lambda x: (x.kind != "terminal", x.tag or "", x.name)
        ):
            t.add_row(v.tag or "", v.name, v.value, v.kind)
            self._rows.append(v.name)

    def _selected(self) -> str | None:
        t = self.query_one("#var_table", DataTable)
        if not self._rows:
            return None
        idx = t.cursor_row or 0
        return self._rows[idx] if idx < len(self._rows) else None

    @on(Button.Pressed, "#var_set")
    def _set(self):
        proj = store.active_project()
        if not proj:
            self.app.notify("No hay proyecto activo.", severity="warning")
            return
        name = self.query_one("#var_name", Input).value.strip()
        value = self.query_one("#var_value", Input).value
        if not name:
            self.app.notify("Indica un nombre de variable.", severity="warning")
            return
        kind = "user" if self.query_one("#var_user", Checkbox).value else None
        try:
            variables = envmod.set_var(
                store.load_project_variables(proj), name, value, kind=kind
            )
        except Exception as e:
            self.app.notify(str(e), severity="error")
            return
        store.save_project_variables(proj, variables)
        self.query_one("#var_name", Input).value = ""
        self.query_one("#var_value", Input).value = ""
        self.reload()
        self.app.notify(f"Variable {name!r} guardada.")

    @on(Button.Pressed, "#var_del")
    def _del(self):
        proj = store.active_project()
        name = self._selected()
        if not (proj and name):
            self.app.notify("Selecciona una variable.", severity="warning")
            return
        variables = envmod.del_var(store.load_project_variables(proj), name)
        store.save_project_variables(proj, variables)
        self.reload()
        self.app.notify(f"Variable {name!r} borrada.", severity="warning")

    @on(Button.Pressed, "#var_reload")
    def _reload(self):
        self.reload()

    @on(Select.Changed, "#var_profile")
    def _profile_changed(self, event):
        p = profilesmod.get(event.value) if isinstance(event.value, str) else None
        self.query_one("#var_profile_desc", Label).update(p.description if p else "")

    @on(Button.Pressed, "#var_apply_profile")
    def _apply_profile(self):
        proj = store.active_project()
        if not proj:
            self.app.notify("No hay proyecto activo.", severity="warning")
            return
        pid = self.query_one("#var_profile", Select).value
        if not isinstance(pid, str):
            self.app.notify("Elige un perfil de la lista.", severity="warning")
            return
        variables = profilesmod.apply_profile(store.load_project_variables(proj), pid)
        store.save_project_variables(proj, variables)
        self.reload()
        p = profilesmod.get(pid)
        self.app.notify(f"Perfil {p.title!r} aplicado ({len(p.values)} variable(s)).")

    @on(DataTable.RowSelected, "#var_table")
    def _fill(self, event: DataTable.RowSelected):
        name = self._selected()
        proj = store.active_project()
        if not (name and proj):
            return
        v = envmod.get_var(store.load_project_variables(proj), name)
        if v:
            self.query_one("#var_name", Input).value = v.name
            self.query_one("#var_value", Input).value = v.value
            self.query_one("#var_user", Checkbox).value = v.kind == "user"
