"""Consola cruda: muestra TODO lo que se envía y se recibe del lector, en dos
niveles y **sin truncar**:

  * **APDU** — comando y respuesta en hex completo + status word interpretado.
  * **Transporte** — la línea cruda por debajo (líneas serie del BomberCat:
    PING/WAIT/READY/APDU:/RESP:…).

Vive en un dock inferior siempre visible. Permite además enviar un APDU a mano.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ...core.apdu import status_word

_MONO = QFont("monospace")
_MONO.setStyleHint(QFont.Monospace)


class RawConsole(QWidget):
    send_apdu = Signal(str)      # el usuario pidió enviar este APDU (hex)
    save_to_project = Signal(str)   # el usuario pidió guardar el log (texto) en el proyecto

    def __init__(self) -> None:
        super().__init__()
        self._log = QPlainTextEdit(readOnly=True)
        self._log.setFont(_MONO)
        self._log.setMaximumBlockCount(5000)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText(
            "APDU hex a enviar (p.ej. 00A404000E325041592E5359532E4444463031)")
        self._entry.setFont(_MONO)
        self._entry.returnPressed.connect(self._on_send)
        send_btn = QPushButton("Enviar")
        send_btn.clicked.connect(self._on_send)
        clear_btn = QPushButton("Limpiar")
        clear_btn.clicked.connect(self._log.clear)
        export_btn = QPushButton("Exportar…")
        export_btn.setToolTip("Guarda toda la consola en un archivo de texto donde quieras")
        export_btn.clicked.connect(self._export)
        save_btn = QPushButton("Guardar en proyecto")
        save_btn.setToolTip("Guarda la consola en logs/ del proyecto activo")
        save_btn.clicked.connect(lambda: self.save_to_project.emit(self.plain_text()))

        row = QHBoxLayout()
        row.addWidget(self._entry, 1)
        row.addWidget(send_btn)
        row.addWidget(clear_btn)
        row.addWidget(export_btn)
        row.addWidget(save_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self._log, 1)
        lay.addLayout(row)

    # -- API (slots invocados desde MainWindow vía señales) ----------------
    def plain_text(self) -> str:
        """Todo el contenido de la consola como texto plano (para exportar)."""
        return self._log.toPlainText()

    def _export(self) -> None:
        from datetime import datetime
        default = f"emvy-consola-{datetime.now():%Y%m%d-%H%M%S}.log"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar consola", default,
                                              "Log (*.log *.txt);;Todos (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.plain_text())
        except OSError as e:
            QMessageBox.warning(self, "Exportar", f"No se pudo guardar: {e}")
            return
        self.info(f"consola exportada a {path}")

    def _on_send(self) -> None:
        hexstr = self._entry.text().strip()
        if hexstr:
            self.send_apdu.emit(hexstr)

    def _html(self, s: str) -> str:
        self._log.appendHtml(s)

    def banner(self, text: str) -> None:
        self._html(f"<span style='color:#888'>── {escape(text)} ──</span>")

    def apdu(self, command: str, response: str, sw: str) -> None:
        ok = sw == "9000"
        col = "#3fb950" if ok else "#f85149"
        meaning = escape(status_word(int(sw[:2], 16), int(sw[2:], 16)))
        self._html(f"<span style='color:#58a6ff'>» {escape(command)}</span>")
        self._html(f"<span style='color:{col}'>« {escape(response) or '(vacío)'}"
                   f"  [{sw}] {meaning}</span>")

    def wire(self, direction: str, text: str, transport: str = "serial") -> None:
        tag = f"<span style='color:#888'>{escape(transport)}</span>"
        if direction == "tx":
            self._html(f"{tag} <span style='color:#d2a8ff'>⇢</span> {escape(text)}")
        elif direction == "rx":
            err = text.startswith("ERR") or "NOCARD" in text
            col = "#e3b341" if err else "#58a6ff"
            self._html(f"{tag} <span style='color:{col}'>⇠ {escape(text)}</span>")
        else:
            self._html(f"{tag} <span style='color:#888'>· {escape(text)}</span>")

    def info(self, text: str) -> None:
        self._html(f"<span style='color:#888'>{escape(text)}</span>")
