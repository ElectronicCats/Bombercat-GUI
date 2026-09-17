"""Panel BomberCat (GUI). Dos responsabilidades separadas en sub-pestañas:

* **Dispositivo** — estado de la placa (firmware + capacidades vía
  `bombercat status`), identificar (LED) y permisos USB (udev). El estado
  alimenta el *gating* por capacidad de los sub-tabs específicos de firmware
  (Tags/Readers/Mifare/… en sesiones posteriores).
* **Flashear** — flashea imágenes `.uf2` **oficiales** (`bombercat flash`) y,
  como sección secundaria "dev", compila/sube el firmware propio de `firmware/`
  con arduino-cli (picotool sube el `.elf`, no `.uf2`; ver CLAUDE.md §12).

Todo el trabajo de hardware pasa por métodos de `MainWindow` (worker en
`QThreadPool`); el panel solo mueve widgets y señales.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...integrations import arduino as ard

_MONO = QFont("monospace")
_MONO.setStyleHint(QFont.Monospace)


class FirmwarePanel(QWidget):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.caps: list[str] = []
        # registro de sub-tabs "gated": (capacidad, widget) — lo llenan las
        # sesiones que añaden Tags/Readers/Mifare/Magspoof/Relay. `_apply_gating`
        # los habilita/deshabilita según las capacidades de la placa.
        self._gated: list[tuple[str, QWidget]] = []

        sub = QLabel(
            "Opera los firmwares BomberCat vía bombercat-tools. La placa corre "
            "UNA imagen a la vez; refresca el estado para ver cuál y sus capacidades."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#8b949e")

        # Puerto serie compartido por todas las acciones (opcional).
        self._port = QLineEdit()
        self._port.setPlaceholderText("puerto (opcional, p.ej. /dev/ttyACM0)")
        self._port.setFixedWidth(240)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Puerto"))
        prow.addWidget(self._port)
        prow.addStretch(1)

        self._sub = QTabWidget()
        self._sub.addTab(self._build_device_tab(), "Dispositivo")
        self._sub.addTab(self._build_flash_tab(), "Flashear")

        self._log = QPlainTextEdit(readOnly=True)
        self._log.setFont(_MONO)

        lay = QVBoxLayout(self)
        lay.addWidget(sub)
        lay.addLayout(prow)
        lay.addWidget(self._sub, 1)
        lay.addWidget(self._log, 1)
        self.reload()

    # -- sub-tab Dispositivo -----------------------------------------------
    def _build_device_tab(self) -> QWidget:
        w = QWidget()
        self._l_name = QLabel("—")
        self._l_ver = QLabel("—")
        self._l_det = QLabel("—")
        self._l_caps = QLabel("—")
        self._l_caps.setWordWrap(True)
        for lbl in (self._l_name, self._l_ver, self._l_det, self._l_caps):
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)

        grid = QVBoxLayout()
        for title, lbl in (
            ("Firmware", self._l_name),
            ("Versión", self._l_ver),
            ("Detección", self._l_det),
            ("Capacidades", self._l_caps),
        ):
            r = QHBoxLayout()
            t = QLabel(title)
            t.setFixedWidth(110)
            t.setStyleSheet("color:#8b949e")
            r.addWidget(t)
            r.addWidget(lbl, 1)
            grid.addLayout(r)

        refresh = QPushButton("Refrescar estado")
        refresh.clicked.connect(lambda: self.win.refresh_device())
        ident = QPushButton("Identificar (LED)")
        ident.setToolTip("Parpadea el LED de la placa para localizarla.")
        ident.clicked.connect(lambda: self.win.identify_device())
        udev = QPushButton("Permisos USB (udev)…")
        udev.setToolTip(
            "Instala reglas udev y grupos (dialout/plugdev) para subir sin sudo.\n"
            "Requiere pkexec (pedirá contraseña de administrador)."
        )
        udev.clicked.connect(lambda: self.win.setup_udev())
        btns = QHBoxLayout()
        btns.addWidget(refresh)
        btns.addWidget(ident)
        btns.addWidget(udev)
        btns.addStretch(1)

        lay = QVBoxLayout(w)
        lay.addLayout(grid)
        lay.addLayout(btns)
        lay.addStretch(1)
        return w

    # -- sub-tab Flashear ---------------------------------------------------
    def _build_flash_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        # Imágenes oficiales (bombercat flash)
        off = QGroupBox("Imágenes oficiales (bombercat-tools)")
        self._image = QComboBox()
        self._image.setMinimumWidth(220)
        rel_img = QPushButton("Recargar lista")
        rel_img.clicked.connect(self.reload_images)
        flash = QPushButton("Flashear imagen")
        flash.clicked.connect(self._do_flash)
        orow = QHBoxLayout()
        orow.addWidget(QLabel("Imagen"))
        orow.addWidget(self._image, 1)
        orow.addWidget(rel_img)
        orow.addWidget(flash)
        ohint = QLabel(
            "Flashear reescribe toda la imagen y BORRA la config guardada "
            "(WiFi/relay de NFCGate). Se pedirá confirmación."
        )
        ohint.setWordWrap(True)
        ohint.setStyleSheet("color:#8b949e")
        ov = QVBoxLayout(off)
        ov.addLayout(orow)
        ov.addWidget(ohint)

        # Firmware propio (dev) — arduino-cli / picotool
        dev = QGroupBox("Firmware propio (dev)")
        self._sketch = QComboBox()
        comp = QPushButton("Compilar")
        comp.clicked.connect(lambda: self._go(False))
        upl = QPushButton("Compilar y subir")
        upl.clicked.connect(lambda: self._go(True))
        rel = QPushButton("Recargar")
        rel.clicked.connect(self.reload)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("Sketch"))
        drow.addWidget(self._sketch, 1)
        drow.addWidget(comp)
        drow.addWidget(upl)
        drow.addWidget(rel)
        dv = QVBoxLayout(dev)
        dv.addLayout(drow)

        lay.addWidget(off)
        lay.addWidget(dev)
        lay.addStretch(1)
        return w

    # -- gating por capacidad (para sesiones futuras) ----------------------
    def register_gated(self, cap: str, widget: QWidget) -> None:
        """Registra un sub-tab que solo aplica si la placa trae `cap`."""
        self._gated.append((cap, widget))
        self._apply_gating()

    def _apply_gating(self) -> None:
        for cap, widget in self._gated:
            idx = self._sub.indexOf(widget)
            if idx >= 0:
                self._sub.setTabEnabled(idx, cap in self.caps)

    def set_status(self, st: dict) -> None:
        """Actualiza la cabecera de estado y re-aplica el gating."""
        self.caps = list(st.get("capabilities", []))
        self._l_name.setText(st.get("name") or "—")
        self._l_ver.setText(st.get("version") or "—")
        self._l_det.setText(st.get("detected") or "—")
        self._l_caps.setText(", ".join(self.caps) or "—")
        self._apply_gating()

    # -- carga de listas ----------------------------------------------------
    def reload(self) -> None:
        """Recarga los sketches locales (sección dev). No toca el venv del vendor."""
        self._sketch.clear()
        if not ard.arduino_cli_available():
            self._log.appendPlainText(
                "arduino-cli no disponible (instálalo para compilar/subir)."
            )
        try:
            for p in ard.list_sketches():
                self._sketch.addItem(p.name, str(p))
        except Exception as e:  # noqa: BLE001
            self._log.appendPlainText(f"No se pudieron listar sketches: {e}")
        if self._sketch.count() == 0:
            self._sketch.addItem("(sin sketches en firmware/)", "")

    def reload_images(self) -> None:
        """Recarga las imágenes oficiales flasheables (arranca el venv del vendor
        la primera vez → va por worker en `MainWindow`)."""
        self.win.reload_flash_images()

    def set_images(self, names: list[str]) -> None:
        cur = self._image.currentData()
        self._image.clear()
        for n in names:
            self._image.addItem(n, n)
        if not names:
            self._image.addItem("(sin imágenes)", "")
        if cur:
            i = self._image.findData(cur)
            if i >= 0:
                self._image.setCurrentIndex(i)

    # -- disparadores -------------------------------------------------------
    def port(self) -> str | None:
        return self._port.text().strip() or None

    def _do_flash(self) -> None:
        name = self._image.currentData()
        if not name:
            self.win.notify.emit("No hay imagen seleccionada.")
            return
        self.win.flash_image(name, port=self.port())

    def _go(self, upload: bool) -> None:
        sketch = self._sketch.currentData()
        if not sketch:
            self.win.notify.emit("No hay sketch seleccionado.")
            return
        self.win.compile_firmware(sketch, upload=upload, port=self.port())

    # -- log (usado por MainWindow) ----------------------------------------
    def log(self, text: str) -> None:
        self._log.appendPlainText(text)

    def log_result(self, res) -> None:
        rc = getattr(res, "returncode", "?")
        out = (getattr(res, "stdout", "") or "")[-2000:]
        err = (getattr(res, "stderr", "") or "")[-800:]
        self._log.appendPlainText(f"── returncode {rc} ──")
        if out:
            self._log.appendPlainText(out)
        if err:
            self._log.appendPlainText(err)
