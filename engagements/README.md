# engagements/

Proyectos EMVy **por cliente/engagement**, versionables aparte de la herramienta.
Cada subcarpeta es un proyecto en ruta con su `project.json` (más `variables.json`,
`captures/`, `pocs/`, `tools/`, `artifacts/`).

Esta carpeta está **vacía a propósito**: la herramienta es genérica y no incluye
datos de clientes. Crea tu engagement con:

```sh
emvy project new <cliente> --path ./engagements/<cliente>
emvy project use ./engagements/<cliente>
```

`emvy project list` (y la pestaña Proyectos de la TUI) descubren automáticamente
los proyectos bajo `engagements/` (ver `config.engagements_dirs()`).

Para PoCs de pago reutilizables (crear cobro → enviar al switch → respuesta →
reverso) usa la pestaña **Cobros** o las plantillas genéricas:

```sh
emvy poc new auth --template iso8583-purchase
emvy var set switch_host <host> --user
emvy var set switch_port <puerto> --user
```

**Regla**: nada específico de cliente entra en `emvy/` ni `firmware/`; todo va aquí.
No compartas el contenido de tus engagements junto con la herramienta.
