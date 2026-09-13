"""Panel PoC (GUI): un **IDE integrado** para automatizar y probar PoCs sobre lo
capturado en la herramienta. Explorador de `<proyecto>/pocs/*.py`, editor de
código Python (resaltado), crear desde plantilla, guardar/eliminar, y ejecutar
al vuelo eligiendo la fuente de la tarjeta (sesión o captura guardada), con
dry-run / allow-write. Panel de referencia con la API de `ctx`. Paridad con la
TUI (`tui/screens/pocs.py`).
"""
from __future__ import annotations

import re

from PySide6.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ...poc.scaffold import scaffold_poc
from ...poc.templates import list_templates
from ...project import store
from ..icons import icon
from ..theme import ACCENT, ACCENT_FG, INFO, MUTED, TEXT, WARNING

_MONO = QFont("JetBrains Mono"); _MONO.setStyleHint(QFont.Monospace); _MONO.setPointSize(10)


def _fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
    f = QTextCharFormat(); f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class _PyHighlighter(QSyntaxHighlighter):
    """Resaltado de sintaxis Python ligero (palabras clave, cadenas, comentarios,
    decoradores, números, nombres def/class) — suficiente para un editor de PoCs."""
    _KW = (r"\b(?:def|class|return|if|elif|else|for|while|try|except|finally|with|as|"
           r"import|from|pass|raise|in|not|and|or|is|None|True|False|lambda|yield|"
           r"global|nonlocal|assert|break|continue|del|await|async)\b")

    def __init__(self, doc) -> None:
        super().__init__(doc)
        self._rules = [
            (re.compile(self._KW), _fmt(ACCENT, bold=True)),
            (re.compile(r"@[\w.]+"), _fmt(WARNING)),
            (re.compile(r"\bself\b|\bctx\b"), _fmt(INFO, italic=True)),
            (re.compile(r"\b\d[\d_.]*\b"), _fmt(WARNING)),
            (re.compile(r"(?<=\bdef )\w+"), _fmt(TEXT, bold=True)),
            (re.compile(r"(?<=\bclass )\w+"), _fmt(TEXT, bold=True)),
        ]
        self._str = _fmt("#86EFAC")       # cadenas verde suave
        self._comment = _fmt(MUTED, italic=True)

    def highlightBlock(self, text: str) -> None:
        for m in re.finditer(r"(\"\"\".*?\"\"\"|'''.*?'''|\".*?\"|'.*?')", text):
            self.setFormat(m.start(), m.end() - m.start(), self._str)
        for pat, fmt in self._rules:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
        c = text.find("#")
        if c >= 0:                        # comentario (aproximado: ignora # en cadenas)
            self.setFormat(c, len(text) - c, self._comment)


class PocPanel(QWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self._open_file: str | None = None

        # -- barra de acciones de archivo ----------------------------------
        self._new_id = QLineEdit(); self._new_id.setPlaceholderText("id del nuevo PoC")
        self._tmpl = QComboBox(); self._tmpl.addItem("(ejemplo)", "")
        for t in list_templates():
            self._tmpl.addItem(t, t)
        b_new = QPushButton("Nuevo"); b_new.clicked.connect(self._new)
        self._b_save = QPushButton("Guardar"); self._b_save.setProperty("accent", True)
        self._b_save.setIcon(icon("download", color=ACCENT_FG)); self._b_save.clicked.connect(self._save)
        b_del = QPushButton("Eliminar"); b_del.clicked.connect(self._delete)
        top = QHBoxLayout()
        top.addWidget(self._new_id, 1); top.addWidget(self._tmpl); top.addWidget(b_new)
        top.addSpacing(12); top.addWidget(self._b_save); top.addWidget(b_del)

        # -- explorador de archivos + referencia ---------------------------
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("Archivos"))
        self._files = QListWidget()
        self._files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._files.currentItemChanged.connect(self._pick)
        lv.addWidget(self._files, 1)
        lv.addWidget(QLabel("Referencia (ctx)"))
        self._ref = QPlainTextEdit(readOnly=True); self._ref.setMaximumHeight(150)
        self._ref.setStyleSheet(f"color:{MUTED};")
        lv.addWidget(self._ref)

        # -- editor de código ----------------------------------------------
        self._editor = QPlainTextEdit(); self._editor.setFont(_MONO)
        self._editor.setTabChangesFocus(False)
        self._editor.setPlaceholderText("Selecciona o crea un PoC para editar su código…")
        self._hl = _PyHighlighter(self._editor.document())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left); split.addWidget(self._editor)
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1)
        split.setSizes([230, 720])

        # -- controles de ejecución ----------------------------------------
        self._card_src = QComboBox()
        self._dry = QCheckBox("dry-run"); self._dry.setChecked(True)
        self._allow = QCheckBox("allow-write")
        run = QPushButton("Ejecutar"); run.setProperty("accent", True)
        run.setIcon(icon("play", color=ACCENT_FG)); run.clicked.connect(self._run)
        rel = QPushButton("Recargar"); rel.clicked.connect(self.reload)
        runrow = QHBoxLayout()
        runrow.addWidget(QLabel("Tarjeta:")); runrow.addWidget(self._card_src, 1)
        runrow.addWidget(self._dry); runrow.addWidget(self._allow)
        runrow.addWidget(rel); runrow.addWidget(run)

        # -- salida ---------------------------------------------------------
        self._log = QPlainTextEdit(readOnly=True); self._log.setFont(_MONO)
        self._log.setMaximumHeight(200)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(runrow)
        lay.addWidget(QLabel("Salida"))
        lay.addWidget(self._log)
        self.reload()

    # -- carga / refresco ---------------------------------------------------
    def reload(self) -> None:
        proj = store.active_project()
        self._ref.setPlainText(self._reference(proj))
        # fuente de la tarjeta
        self._card_src.clear()
        self._card_src.addItem("Sesión (última captura)", None)
        if proj:
            for p in store.list_captures(proj):
                self._card_src.addItem(f"Captura: {p.stem}", p.stem)
        # lista de archivos
        self._files.blockSignals(True)
        self._files.clear()
        if proj and proj.pocs_dir.exists():
            for f in sorted(proj.pocs_dir.glob("*.py")):
                it = QListWidgetItem(icon("flask", color="#CBD5E1"), f.name)
                it.setData(Qt.UserRole, f.name)
                self._files.addItem(it)
        if self._files.count() == 0:
            self._files.addItem(QListWidgetItem("(sin PoCs — crea uno arriba)"))
        self._files.blockSignals(False)

    def _reference(self, proj) -> str:
        varlist = ""
        if proj:
            try:
                names = [v.name for v in store.load_project_variables(proj)][:8]
                varlist = "\nvariables: " + ", ".join(names) if names else ""
            except Exception:
                pass
        return ("@poc(id=…, title=…, category=…, severity=…, authorization=…)\n"
                "def run(ctx):\n"
                "  ctx.card         → EmvCard de la tarjeta elegida\n"
                "  ctx.var(name)/ctx.require(name) → variables del proyecto\n"
                "  ctx.http()       → cliente HTTP (evidencia, solo-lectura salvo allow-write)\n"
                "  ctx.save_evidence(name, data)\n"
                "  ctx.finding(...) / ctx.result(status, summary)\n"
                "Resultado + evidencias → <proyecto>/poc_runs/<ts>-<id>/" + varlist)

    # -- interacción --------------------------------------------------------
    def _pick(self, cur, _prev=None) -> None:
        if cur is None:
            return
        fname = cur.data(Qt.UserRole)
        if not fname:
            return
        self._open(fname)

    def _open(self, fname: str) -> None:
        proj = store.active_project()
        if not proj:
            return
        try:
            self._editor.setPlainText((proj.pocs_dir / fname).read_text())
        except Exception as e:  # noqa: BLE001
            self.win.notify.emit(f"Abrir PoC: {e}"); return
        self._open_file = fname

    def _new(self) -> None:
        proj = store.active_project()
        if not proj:
            self.win.notify.emit("No hay proyecto activo."); return
        pid = self._new_id.text().strip()
        if not pid:
            self.win.notify.emit("Indica un id para el PoC."); return
        try:
            path = scaffold_poc(proj.pocs_dir, pid, template=self._tmpl.currentData() or None)
        except Exception as e:  # noqa: BLE001
            self.win.notify.emit(f"Crear PoC: {e}"); return
        self._new_id.clear()
        self.reload()
        self._select_file(path.name)
        self.win.notify.emit(f"PoC creado: {path.name}")

    def _save(self) -> None:
        proj = store.active_project()
        if not (proj and self._open_file):
            self.win.notify.emit("No hay archivo abierto que guardar."); return
        try:
            (proj.pocs_dir / self._open_file).write_text(self._editor.toPlainText())
        except Exception as e:  # noqa: BLE001
            self.win.notify.emit(f"Guardar: {e}"); return
        self.win.notify.emit(f"Guardado: {self._open_file}")

    def _delete(self) -> None:
        proj = store.active_project()
        if not (proj and self._open_file):
            return
        try:
            (proj.pocs_dir / self._open_file).unlink()
        except Exception as e:  # noqa: BLE001
            self.win.notify.emit(f"Eliminar: {e}"); return
        self.win.notify.emit(f"Eliminado: {self._open_file}")
        self._open_file = None; self._editor.clear()
        self.reload()

    def _select_file(self, fname: str) -> None:
        for i in range(self._files.count()):
            if self._files.item(i).data(Qt.UserRole) == fname:
                self._files.setCurrentRow(i); return

    def _run(self) -> None:
        if not self._open_file:
            self.win.notify.emit("Abre o crea un PoC primero."); return
        self._save()                             # guarda el editor antes de ejecutar
        poc_id = self._open_file[:-3] if self._open_file.endswith(".py") else self._open_file
        self._log.appendPlainText(f"→ ejecutando {poc_id}…")
        self.win.run_poc(poc_id, dry_run=self._dry.isChecked(),
                         allow_write=self._allow.isChecked(),
                         capture_name=self._card_src.currentData())

    def show_result(self, meta, result, run_dir) -> None:
        self._log.appendPlainText(f"══ {meta.title or meta.id} — {result.status} ══")
        for f in getattr(result, "findings", []) or []:
            self._log.appendPlainText(f"  [{f.severity}] {f.title}: {f.detail}")
        summ = getattr(result, "summary", None)
        if isinstance(summ, str) and summ:
            self._log.appendPlainText(summ)
        self._log.appendPlainText(f"  run: {run_dir}")
