"""Panel Herramientas (GUI): sub-pestañas Flags, ISO 8583 y Escritura.

Reutiliza `core.search`, `payments.iso8583`/`iso_host` y `core.cardwrite`
(igual que la TUI). La consola cruda del dock inferior es aparte (transporte).
"""
from __future__ import annotations

from html import escape

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
    QLineEdit, QPlainTextEdit, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core.hexutil import from_hex, to_hex
from ...core.search import search_flags, search_regex
from ...payments import iso8583

_MONO = QFont("monospace"); _MONO.setStyleHint(QFont.Monospace)


def _log() -> QPlainTextEdit:
    w = QPlainTextEdit(readOnly=True); w.setFont(_MONO); w.setMaximumBlockCount(4000)
    return w


class ToolsPanel(QTabWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.flags = _FlagsTool(win)
        self.iso = _IsoTool(win)
        self.write = _WriteTool(win)
        self.addTab(self.flags, "Flags")
        self.addTab(self.iso, "ISO 8583")
        self.addTab(self.write, "Escritura")

    # reexpuestos para MainWindow (resultados de workers)
    def log_write(self, op, resp) -> None:
        self.write.log_result(op, resp)
        self.setCurrentWidget(self.write)

    def iso_response(self, resp) -> None:
        self.iso.show_response(resp)


class _FlagsTool(QWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self._pat = QLineEdit(r"flag\{[^}]+\}")
        search = QPushButton("Buscar patrón"); search.clicked.connect(self._search)
        default = QPushButton("Patrones por defecto"); default.clicked.connect(self._default)
        row = QHBoxLayout(); row.addWidget(self._pat, 1); row.addWidget(search); row.addWidget(default)
        self._log = _log()
        lay = QVBoxLayout(self); lay.addLayout(row); lay.addWidget(self._log, 1)

    def _dump(self):
        d = self.win.last_dump
        if d is None:
            self._log.appendPlainText("No hay captura. Ve a Explorador → Capturar primero.")
        return d

    def _search(self) -> None:
        d = self._dump()
        if d:
            self._render(search_regex(d.all_blobs(), self._pat.text() or r"flag\{[^}]+\}"))

    def _default(self) -> None:
        d = self._dump()
        if d:
            self._render(search_flags(d.all_blobs()))

    def _render(self, hits) -> None:
        if not hits:
            self._log.appendPlainText("Sin coincidencias.")
            return
        self._log.appendPlainText(f"══ {len(hits)} posible(s) flag(s) ══")
        for h in hits:
            self._log.appendPlainText(f"  {h.match}\n    en {h.source} ({h.where})\n    ctx: …{h.context}…")


class _IsoTool(QWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self._fields: dict[int, bytes] = {}
        self._built: bytes | None = None
        self._des: list[int] = []

        self._mti = QLineEdit("0200"); self._mti.setFixedWidth(64)
        self._de = QLineEdit(); self._de.setPlaceholderText("DE (nº)"); self._de.setFixedWidth(80)
        self._val = QLineEdit(); self._val.setPlaceholderText("valor (hex o texto)")
        self._hex = QCheckBox("hex"); self._hex.setChecked(True)
        setb = QPushButton("Set campo"); setb.clicked.connect(self._set)
        delb = QPushButton("Quitar sel."); delb.clicked.connect(self._del)
        row1 = QHBoxLayout()
        for x in (self._mti, self._de, self._val, self._hex, setb, delb):
            row1.addWidget(x)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["DE", "nombre", "valor (hex)"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        build = QPushButton("Construir"); build.clicked.connect(self._build)
        self._host = QLineEdit("127.0.0.1"); self._port = QLineEdit("0"); self._port.setFixedWidth(64)
        self._hdr = QComboBox()
        for label, val in (("hdr 2B", 2), ("sin hdr", 0), ("hdr 4B", 4)):
            self._hdr.addItem(label, val)
        send = QPushButton("Enviar"); send.clicked.connect(self._send)
        row2 = QHBoxLayout()
        row2.addWidget(build); row2.addWidget(self._host, 1)
        row2.addWidget(self._port); row2.addWidget(self._hdr); row2.addWidget(send)

        self._log = _log()
        lay = QVBoxLayout(self)
        lay.addLayout(row1); lay.addWidget(self._table); lay.addLayout(row2); lay.addWidget(self._log, 1)

    def _refresh(self) -> None:
        self._des = sorted(self._fields)
        self._table.setRowCount(len(self._des))
        for i, de in enumerate(self._des):
            spec = iso8583.DEFAULT_SPEC.get(de)
            for j, val in enumerate((str(de), spec.name if spec else "?", to_hex(self._fields[de]))):
                self._table.setItem(i, j, QTableWidgetItem(val))

    def _set(self) -> None:
        try:
            de = int(self._de.text())
            val = from_hex(self._val.text().strip()) if self._hex.isChecked() \
                else self._val.text().encode("latin-1")
        except ValueError:
            self.win.notify.emit("DE o valor inválido."); return
        self._fields[de] = val
        self._de.clear(); self._val.clear(); self._refresh()

    def _del(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._des):
            self._fields.pop(self._des[row], None); self._refresh()

    def _build(self) -> None:
        try:
            msg = iso8583.build(self._mti.text().strip(), self._fields)
        except Exception as e:  # noqa: BLE001
            self.win.notify.emit(f"No se pudo construir: {e}"); return
        self._built = msg
        self._log.appendPlainText("Construido: " + to_hex(msg))
        self._log.appendPlainText(iso8583.translate(msg).text())

    def _send(self) -> None:
        if not self._built:
            self.win.notify.emit("Construye el mensaje primero."); return
        port = self._port.text().strip()
        if not port.isdigit() or int(port) == 0:
            self.win.notify.emit("Indica un puerto válido."); return
        self._log.appendPlainText(f"→ enviando a {self._host.text()}:{port}…")
        self.win.send_iso8583(self._host.text().strip(), int(port), self._built,
                              self._hdr.currentData())

    def show_response(self, resp: bytes) -> None:
        self._log.appendPlainText("Respuesta: " + (to_hex(resp) or "(vacía)"))
        if resp:
            try:
                self._log.appendPlainText(iso8583.translate(resp).text())
            except Exception as e:  # noqa: BLE001
                self._log.appendPlainText(f"no parseable como ISO 8583: {e}")


_OPS = [("UPDATE RECORD", "record"), ("UPDATE BINARY", "binary"),
        ("PUT DATA", "data"), ("APPEND RECORD", "append")]


class _WriteTool(QWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        warn = QPlainTextEdit(
            "⚠ Modifica la tarjeta (puede ser irreversible). Solo tarjetas propias/de "
            "laboratorio; muchas escrituras exigen canal seguro (SW 6982/6985).")
        warn.setReadOnly(True); warn.setMaximumHeight(48)

        self._op = QComboBox()
        for label, val in _OPS:
            self._op.addItem(label, val)
        self._sfi = QLineEdit(); self._sfi.setPlaceholderText("SFI"); self._sfi.setFixedWidth(70)
        self._num = QLineEdit(); self._num.setPlaceholderText("registro / offset"); self._num.setFixedWidth(120)
        self._tag = QLineEdit(); self._tag.setPlaceholderText("tag (PUT DATA)"); self._tag.setFixedWidth(120)
        row1 = QHBoxLayout()
        for x in (self._op, self._sfi, self._num, self._tag):
            row1.addWidget(x)
        row1.addStretch(1)
        self._data = QLineEdit(); self._data.setPlaceholderText("datos en hex")
        write = QPushButton("Escribir"); write.clicked.connect(self._write)
        row2 = QHBoxLayout(); row2.addWidget(self._data, 1); row2.addWidget(write)

        self._log = _log()
        lay = QVBoxLayout(self)
        lay.addWidget(warn); lay.addLayout(row1); lay.addLayout(row2); lay.addWidget(self._log, 1)

    def _write(self) -> None:
        op = self._op.currentData()
        try:
            data = from_hex(self._data.text().strip())
        except ValueError:
            self.win.notify.emit("Datos hex inválidos."); return
        params = {"data": data}
        try:
            if op == "record":
                params["sfi"] = int(self._sfi.text()); params["record"] = int(self._num.text())
            elif op == "binary":
                params["offset"] = int(self._num.text() or "0")
                sfi = self._sfi.text().strip(); params["sfi"] = int(sfi) if sfi else None
            elif op == "data":
                params["tag"] = int(self._tag.text().strip(), 16)
            elif op == "append":
                params["sfi"] = int(self._sfi.text())
        except ValueError:
            self.win.notify.emit("SFI/registro/offset/tag inválido."); return
        self._log.appendPlainText(f"→ {op} {to_hex(data)}…")
        self.win.write_op(op, params)

    def log_result(self, op: str, resp) -> None:
        from ...core import cardwrite
        self._log.appendPlainText(f"{op.upper()}  SW {resp.sw_hex}  {cardwrite.write_status(resp.sw)}")
        if resp.data:
            self._log.appendPlainText("   data: " + to_hex(resp.data))
