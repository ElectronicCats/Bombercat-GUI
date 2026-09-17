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
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
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

        # Sub-tabs específicos de firmware — habilitados por capacidad (gating).
        tags_tab = self._build_tags_tab()
        self._sub.addTab(tags_tab, "Tags")
        self.register_gated("tags", tags_tab)
        readers_tab = self._build_readers_tab()
        self._sub.addTab(readers_tab, "Readers")
        self.register_gated("readers", readers_tab)
        magspoof_tab = self._build_magspoof_tab()
        self._sub.addTab(magspoof_tab, "Magspoof")
        self.register_gated("magspoof", magspoof_tab)

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

    # -- sub-tab Tags (gated:tags) -----------------------------------------
    def _build_tags_tab(self) -> QWidget:
        w = QWidget()
        hint = QLabel(
            "Lee un tag NFC (DetectTags): espera a que se acerque una tarjeta y "
            "muestra UID, tecnología, protocolo y modelo resuelto host-side."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e")

        self._tags_timeout = QSpinBox()
        self._tags_timeout.setRange(1, 120)
        self._tags_timeout.setValue(15)
        self._tags_timeout.setSuffix(" s")
        read = QPushButton("Leer tag")
        read.clicked.connect(lambda: self.win.tags_read(self._tags_timeout.value()))
        row = QHBoxLayout()
        row.addWidget(QLabel("Timeout"))
        row.addWidget(self._tags_timeout)
        row.addWidget(read)
        row.addStretch(1)

        self._tags_table = self._kv_table()

        lay = QVBoxLayout(w)
        lay.addWidget(hint)
        lay.addLayout(row)
        lay.addWidget(self._tags_table, 1)
        return w

    # -- sub-tab Readers (gated:readers) -----------------------------------
    def _build_readers_tab(self) -> QWidget:
        w = QWidget()
        hint = QLabel(
            "Detecta un lector/POS (DetectReaders): espera a que un terminal "
            "consulte la placa y muestra su primer APDU (p.ej. SELECT PPSE)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e")

        self._readers_timeout = QSpinBox()
        self._readers_timeout.setRange(1, 120)
        self._readers_timeout.setValue(15)
        self._readers_timeout.setSuffix(" s")
        read = QPushButton("Detectar lector")
        read.clicked.connect(
            lambda: self.win.readers_read(self._readers_timeout.value())
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Timeout"))
        row.addWidget(self._readers_timeout)
        row.addWidget(read)
        row.addStretch(1)

        self._readers_table = self._kv_table()

        lay = QVBoxLayout(w)
        lay.addWidget(hint)
        lay.addLayout(row)
        lay.addWidget(self._readers_table, 1)
        return w

    # -- sub-tab Magspoof (gated:magspoof) ---------------------------------
    def _build_magspoof_tab(self) -> QWidget:
        w = QWidget()
        hint = QLabel(
            "Emulación de banda magnética (magspoof): inspecciona la tarjeta "
            "activa, reprodúcela (swipe), gestiona el store de tarjetas y emula "
            "Visa por NFC contactless."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e")

        # -- tarjeta activa: show / play / nfc visa --
        show = QPushButton("Mostrar (show)")
        show.clicked.connect(lambda: self.win.magspoof_show())
        play = QPushButton("Reproducir (play)")
        play.clicked.connect(lambda: self.win.magspoof_play())
        nfc = QPushButton("Emular Visa (NFC)")
        nfc.clicked.connect(lambda: self.win.magspoof_nfc_visa())
        arow = QHBoxLayout()
        arow.addWidget(show)
        arow.addWidget(play)
        arow.addWidget(nfc)
        arow.addStretch(1)
        self._magspoof_table = self._kv_table()
        active = QGroupBox("Tarjeta activa")
        al = QVBoxLayout(active)
        al.addLayout(arow)
        al.addWidget(self._magspoof_table, 1)

        # -- store persistente: list / select / add --
        lst = QPushButton("Listar (card list)")
        lst.clicked.connect(lambda: self.win.magspoof_card_list())
        self._card_name = QComboBox()
        self._card_name.setEditable(True)
        self._card_name.setMinimumWidth(160)
        sel = QPushButton("Seleccionar")
        sel.clicked.connect(
            lambda: self.win.magspoof_card_select(self._card_name.currentText().strip())
        )
        srow = QHBoxLayout()
        srow.addWidget(lst)
        srow.addWidget(QLabel("Tarjeta"))
        srow.addWidget(self._card_name)
        srow.addWidget(sel)
        srow.addStretch(1)

        self._cards_table = QTableWidget(0, 2)
        self._cards_table.setHorizontalHeaderLabels(["Tarjeta", "Datos"])
        self._cards_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self._cards_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._cards_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cards_table.verticalHeader().setVisible(False)

        self._add_name = QLineEdit()
        self._add_name.setPlaceholderText("nombre")
        self._add_name.setFixedWidth(120)
        self._add_t1 = QLineEdit()
        self._add_t1.setPlaceholderText("Track 1 (%B…?)")
        self._add_t2 = QLineEdit()
        self._add_t2.setPlaceholderText("Track 2 (;…?)")
        add = QPushButton("Agregar (card add)")
        add.clicked.connect(
            lambda: self.win.magspoof_card_add(
                self._add_name.text().strip(),
                self._add_t1.text().strip(),
                self._add_t2.text().strip(),
            )
        )
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Nombre"))
        frow.addWidget(self._add_name)
        frow.addWidget(self._add_t1, 1)
        frow.addWidget(self._add_t2, 1)
        frow.addWidget(add)

        store = QGroupBox("Tarjetas guardadas")
        sl = QVBoxLayout(store)
        sl.addLayout(srow)
        sl.addWidget(self._cards_table, 1)
        sl.addLayout(frow)

        lay = QVBoxLayout(w)
        lay.addWidget(hint)
        lay.addWidget(active, 1)
        lay.addWidget(store, 1)
        return w

    def show_magspoof(self, data) -> None:
        """Pinta `magspoof show --json` (t1/t2/btn + `analysis` aplanado)."""
        if isinstance(data, list):
            data = data[0] if data else {}
        data = data or {}
        flat = {k: v for k, v in data.items() if k != "analysis"}
        for k, v in (data.get("analysis") or {}).items():
            flat[f"analysis.{k}"] = v
        self._fill_kv(self._magspoof_table, flat)

    def show_cards(self, cards) -> None:
        """Pinta `magspoof card list --json` (una fila por tarjeta) y puebla el
        combo de selección con los nombres."""
        cards = cards if isinstance(cards, list) else [cards] if cards else []
        self._cards_table.setRowCount(len(cards))
        names: list[str] = []
        for i, c in enumerate(cards):
            name = str(c.get("name", "")) if isinstance(c, dict) else str(c)
            names.append(name)
            rest = (
                {k: v for k, v in c.items() if k != "name"}
                if isinstance(c, dict)
                else {}
            )
            self._cards_table.setItem(i, 0, QTableWidgetItem(name))
            self._cards_table.setItem(
                i, 1, QTableWidgetItem(", ".join(f"{k}={v}" for k, v in rest.items()))
            )
        cur = self._card_name.currentText()
        self._card_name.clear()
        self._card_name.addItems([n for n in names if n])
        if cur:
            self._card_name.setEditText(cur)

    def _kv_table(self) -> QTableWidget:
        """Tabla Campo/Valor genérica (las claves del JSON varían por firmware)."""
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["Campo", "Valor"])
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        return t

    @staticmethod
    def _fill_kv(table: QTableWidget, data: dict) -> None:
        rows = list(data.items())
        table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(str(k)))
            table.setItem(i, 1, QTableWidgetItem("—" if v is None else str(v)))

    def show_tag(self, data) -> None:
        """Pinta el resultado de `tags read --json` (un objeto) en la tabla."""
        if isinstance(data, list):
            data = data[0] if data else {}
        self._fill_kv(self._tags_table, data or {})

    def show_reader(self, data) -> None:
        """Pinta el resultado de `readers read --json` (un objeto) en la tabla."""
        if isinstance(data, list):
            data = data[0] if data else {}
        self._fill_kv(self._readers_table, data or {})

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
