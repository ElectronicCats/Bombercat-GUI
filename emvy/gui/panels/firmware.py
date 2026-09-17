"""Paneles BomberCat (GUI) — **un Tab de nivel superior por firmware** (ADR-001).

La placa corre **una** imagen a la vez; cada firmware oficial es un modo/herramienta
distinto, así que cada uno es su propio panel (Tab), no un sub-tab de un panel único:

* **DevicePanel** (*Dispositivo*) — control-plane común, **siempre habilitado**: estado de
  la placa (firmware + capacidades vía `bombercat status`), identificar (LED), permisos USB
  (udev), flasheo de imágenes `.uf2` **oficiales** (`bombercat flash`) y, como sección
  secundaria "dev", compilar/subir el firmware propio de `firmware/` con arduino-cli.
  Es el **único** panel que posee el puerto serie compartido y el que flashea.
* **TagsPanel** / **ReadersPanel** / **MagspoofPanel** — paneles **gated** por capacidad
  (`tags`/`readers`/`magspoof`): arrancan deshabilitados y `set_status()` los habilita solo
  si la placa corre el firmware que aporta esa capacidad.

`BaseFirmwarePanel` centraliza el gating (`set_status` → `setEnabled(cap in caps)`), el acceso
al **puerto único** (`port()` → `MainWindow.firmware_port()`) y el `log`/`log_result`. Todo el
trabajo de hardware pasa por métodos de `MainWindow` (worker en `QThreadPool`); los paneles
solo mueven widgets y señales.
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
    QVBoxLayout,
    QWidget,
)

from ...integrations import arduino as ard

_MONO = QFont("monospace")
_MONO.setStyleHint(QFont.Monospace)


class BaseFirmwarePanel(QWidget):
    """Base común de los paneles de firmware. Aporta el gating por capacidad, el
    acceso al puerto serie compartido y el log. Los paneles gated declaran su
    `capability`; el control-plane deja `capability = None` (siempre habilitado).
    """

    #: capacidad que habilita el panel (`None` = control-plane, siempre activo).
    capability: str | None = None
    #: imagen oficial a flashear para habilitar este firmware (para la pista de gating).
    needs_image: str = ""

    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.caps: list[str] = []
        self._log = QPlainTextEdit(readOnly=True)
        self._log.setFont(_MONO)
        if self.capability is not None:
            self.setEnabled(False)  # gated: deshabilitado hasta que llegue el status

    # -- puerto serie único (vive en el DevicePanel; los demás lo leen) -----
    def port(self) -> str | None:
        return self.win.firmware_port()

    # -- gating por capacidad ----------------------------------------------
    def set_status(self, st: dict) -> None:
        """Actualiza las capacidades y (si el panel es gated) se habilita/deshabilita."""
        self.caps = list(st.get("capabilities", []))
        if self.capability is not None:
            self.setEnabled(self.capability in self.caps)
        self.on_status(st)

    def on_status(self, st: dict) -> None:
        """Hook para subclases (p.ej. el DevicePanel pinta la cabecera)."""

    # -- log ----------------------------------------------------------------
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

    # -- helpers de UI compartidos -----------------------------------------
    @staticmethod
    def _hint(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#8b949e")
        return lbl

    def _gate_hint(self) -> QLabel:
        """Pista para paneles gated: cómo habilitarlos cuando la placa no trae su
        firmware (el flasheo vive en el panel Dispositivo)."""
        img = self.needs_image or "el firmware correspondiente"
        return self._hint(
            f"Esta función necesita el firmware «{img}». Si el panel está "
            "deshabilitado, ve a Dispositivo → Flashear y flashea esa imagen."
        )

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


class DevicePanel(BaseFirmwarePanel):
    """Control-plane común (siempre habilitado): estado + flasheo + firmware propio.
    Posee el **puerto serie único** que el resto de paneles lee vía `MainWindow`."""

    capability = None

    def __init__(self, win) -> None:
        super().__init__(win)
        sub = self._hint(
            "Estado y flasheo de la placa BomberCat vía bombercat-tools. La placa "
            "corre UNA imagen a la vez; refresca el estado para ver cuál y sus "
            "capacidades — se habilitan los paneles de firmware correspondientes."
        )

        # Puerto serie compartido por TODOS los paneles de firmware.
        self._port = QLineEdit()
        self._port.setPlaceholderText("puerto (opcional, p.ej. /dev/ttyACM0)")
        self._port.setFixedWidth(240)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Puerto"))
        prow.addWidget(self._port)
        prow.addStretch(1)

        lay = QVBoxLayout(self)
        lay.addWidget(sub)
        lay.addLayout(prow)
        lay.addWidget(self._build_device_group())
        lay.addWidget(self._build_flash_group())
        lay.addWidget(self._log, 1)
        self.reload()

    # -- puerto (lo posee este panel) --------------------------------------
    def port(self) -> str | None:
        return self._port.text().strip() or None

    # -- grupo Dispositivo --------------------------------------------------
    def _build_device_group(self) -> QGroupBox:
        box = QGroupBox("Dispositivo")
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

        v = QVBoxLayout(box)
        v.addLayout(grid)
        v.addLayout(btns)
        return box

    # -- grupo Flashear -----------------------------------------------------
    def _build_flash_group(self) -> QGroupBox:
        box = QGroupBox("Flashear")
        lay = QVBoxLayout(box)

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
        ohint = self._hint(
            "Flashear reescribe toda la imagen y BORRA la config guardada "
            "(WiFi/relay de NFCGate). Se pedirá confirmación."
        )
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
        return box

    # -- cabecera de estado -------------------------------------------------
    def on_status(self, st: dict) -> None:
        self._l_name.setText(st.get("name") or "—")
        self._l_ver.setText(st.get("version") or "—")
        self._l_det.setText(st.get("detected") or "—")
        self._l_caps.setText(", ".join(self.caps) or "—")

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


class TagsPanel(BaseFirmwarePanel):
    """DetectTags (gated:tags): lee un tag NFC y muestra UID/tech/protocolo/modelo."""

    capability = "tags"
    needs_image = "DetectTags"

    def __init__(self, win) -> None:
        super().__init__(win)
        self._timeout = QSpinBox()
        self._timeout.setRange(1, 120)
        self._timeout.setValue(15)
        self._timeout.setSuffix(" s")
        read = QPushButton("Leer tag")
        read.clicked.connect(lambda: self.win.tags_read(self._timeout.value()))
        row = QHBoxLayout()
        row.addWidget(QLabel("Timeout"))
        row.addWidget(self._timeout)
        row.addWidget(read)
        row.addStretch(1)

        self._table = self._kv_table()

        lay = QVBoxLayout(self)
        lay.addWidget(self._gate_hint())
        lay.addWidget(
            self._hint(
                "Lee un tag NFC (DetectTags): espera a que se acerque una tarjeta y "
                "muestra UID, tecnología, protocolo y modelo resuelto host-side."
            )
        )
        lay.addLayout(row)
        lay.addWidget(self._table, 1)
        lay.addWidget(self._log, 1)

    def show_tag(self, data) -> None:
        """Pinta el resultado de `tags read --json` (un objeto) en la tabla."""
        if isinstance(data, list):
            data = data[0] if data else {}
        self._fill_kv(self._table, data or {})


class ReadersPanel(BaseFirmwarePanel):
    """DetectReaders (gated:readers): detecta un lector/POS y su primer APDU."""

    capability = "readers"
    needs_image = "DetectReaders"

    def __init__(self, win) -> None:
        super().__init__(win)
        self._timeout = QSpinBox()
        self._timeout.setRange(1, 120)
        self._timeout.setValue(15)
        self._timeout.setSuffix(" s")
        read = QPushButton("Detectar lector")
        read.clicked.connect(lambda: self.win.readers_read(self._timeout.value()))
        row = QHBoxLayout()
        row.addWidget(QLabel("Timeout"))
        row.addWidget(self._timeout)
        row.addWidget(read)
        row.addStretch(1)

        self._table = self._kv_table()

        lay = QVBoxLayout(self)
        lay.addWidget(self._gate_hint())
        lay.addWidget(
            self._hint(
                "Detecta un lector/POS (DetectReaders): espera a que un terminal "
                "consulte la placa y muestra su primer APDU (p.ej. SELECT PPSE)."
            )
        )
        lay.addLayout(row)
        lay.addWidget(self._table, 1)
        lay.addWidget(self._log, 1)

    def show_reader(self, data) -> None:
        """Pinta el resultado de `readers read --json` (un objeto) en la tabla."""
        if isinstance(data, list):
            data = data[0] if data else {}
        self._fill_kv(self._table, data or {})


class MagspoofPanel(BaseFirmwarePanel):
    """magspoof (gated:magspoof): inspecciona/reproduce banda magnética + store."""

    capability = "magspoof"
    needs_image = "magspoof"

    def __init__(self, win) -> None:
        super().__init__(win)
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
        self._table = self._kv_table()
        active = QGroupBox("Tarjeta activa")
        al = QVBoxLayout(active)
        al.addLayout(arow)
        al.addWidget(self._table, 1)

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

        lay = QVBoxLayout(self)
        lay.addWidget(self._gate_hint())
        lay.addWidget(
            self._hint(
                "Emulación de banda magnética (magspoof): inspecciona la tarjeta "
                "activa, reprodúcela (swipe), gestiona el store de tarjetas y emula "
                "Visa por NFC contactless."
            )
        )
        lay.addWidget(active, 1)
        lay.addWidget(store, 1)
        lay.addWidget(self._log, 1)

    def show_magspoof(self, data) -> None:
        """Pinta `magspoof show --json` (t1/t2/btn + `analysis` aplanado)."""
        if isinstance(data, list):
            data = data[0] if data else {}
        data = data or {}
        flat = {k: v for k, v in data.items() if k != "analysis"}
        for k, v in (data.get("analysis") or {}).items():
            flat[f"analysis.{k}"] = v
        self._fill_kv(self._table, flat)

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


class MifarePanel(BaseFirmwarePanel):
    """MifareClassic (gated:mifare): recuperación de claves + volcado/restauración.

    Flujo guiado en tres pasos, con ficheros intermedios en `<proyecto>/artifacts/`:
    **Claves** (diccionario por defecto) → **Recuperar+Volcar** (check → keyfile →
    dump → JSON) → **Restaurar** (escribe un dump de vuelta a la tarjeta). El dump
    es un JSON de tarjeta Mifare (uid + bloques por sector), NO un CardDump EMV, así
    que se guarda como artefacto del proyecto, no como captura del Explorador.
    """

    capability = "mifare"
    needs_image = "MifareClassic"

    def __init__(self, win) -> None:
        super().__init__(win)
        lay = QVBoxLayout(self)
        lay.addWidget(self._gate_hint())
        lay.addWidget(
            self._hint(
                "Mifare Classic (MifareClassic): acerca una tarjeta y el firmware "
                "abre la sesión solo. «Recuperar y volcar» prueba el diccionario de "
                "claves contra cada sector, guarda las recuperadas y vuelca la "
                "tarjeta a un JSON en artifacts/. «Restaurar» escribe un dump de "
                "vuelta a una tarjeta reescribible."
            )
        )
        lay.addWidget(self._build_dump_group())
        lay.addWidget(self._build_restore_group(), 1)
        lay.addWidget(self._log, 1)

    # -- grupo recuperación + volcado --------------------------------------
    def _build_dump_group(self) -> QGroupBox:
        box = QGroupBox("Recuperar claves y volcar")
        v = QVBoxLayout(box)

        self._sectors = QSpinBox()
        self._sectors.setRange(1, 40)
        self._sectors.setValue(16)
        self._sectors.setToolTip("16 = tarjeta de 1K; 40 = 4K.")
        keys = QPushButton("Ver claves por defecto")
        keys.clicked.connect(lambda: self.win.mifare_keys())
        dump = QPushButton("Recuperar y volcar")
        dump.setToolTip(
            "check → recupera las claves de cada sector → dump → JSON en "
            "artifacts/. Requiere un proyecto activo."
        )
        dump.clicked.connect(lambda: self.win.mifare_dump(self._sectors.value()))
        row = QHBoxLayout()
        row.addWidget(QLabel("Sectores"))
        row.addWidget(self._sectors)
        row.addWidget(keys)
        row.addWidget(dump)
        row.addStretch(1)
        v.addLayout(row)

        # tabla de claves por defecto (nombre → clave)
        self._keys_table = QTableWidget(0, 2)
        self._keys_table.setHorizontalHeaderLabels(["Clave", "Valor"])
        self._keys_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._keys_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._keys_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._keys_table.verticalHeader().setVisible(False)
        v.addWidget(self._keys_table)

        # resumen del último dump (uid + nº de sectores)
        self._dump_table = self._kv_table()
        v.addWidget(self._dump_table)
        return box

    # -- grupo restauración -------------------------------------------------
    def _build_restore_group(self) -> QGroupBox:
        box = QGroupBox("Restaurar")
        v = QVBoxLayout(box)
        self._dumps = QComboBox()
        self._dumps.setMinimumWidth(220)
        rel = QPushButton("Recargar dumps")
        rel.clicked.connect(self.reload_dumps)
        restore = QPushButton("Restaurar a la tarjeta")
        restore.setToolTip(
            "Escribe el dump seleccionado de vuelta a una tarjeta Mifare "
            "reescribible. No reescribe el bloque 0 (UID)."
        )
        restore.clicked.connect(self._do_restore)
        row = QHBoxLayout()
        row.addWidget(QLabel("Dump"))
        row.addWidget(self._dumps, 1)
        row.addWidget(rel)
        row.addWidget(restore)
        v.addLayout(row)
        v.addWidget(
            self._hint(
                "Los dumps son los JSON de artifacts/ generados por «Recuperar y "
                "volcar». Restaurar sobrescribe los bloques de datos y trailers "
                "(claves + access bits) de la tarjeta."
            )
        )
        return box

    # -- renderizadores -----------------------------------------------------
    def show_keys(self, keys) -> None:
        """Pinta `mifare keys --json` (una fila por clave por defecto)."""
        keys = keys if isinstance(keys, list) else [keys] if keys else []
        self._keys_table.setRowCount(len(keys))
        for i, k in enumerate(keys):
            name = str(k.get("name", "")) if isinstance(k, dict) else str(k)
            val = str(k.get("key", "")) if isinstance(k, dict) else ""
            self._keys_table.setItem(i, 0, QTableWidgetItem(name))
            self._keys_table.setItem(i, 1, QTableWidgetItem(val))

    def show_dump(self, data) -> None:
        """Resume el JSON de `mifare dump` (uid + nº de sectores leídos)."""
        if isinstance(data, list):
            data = data[0] if data else {}
        data = data or {}
        sectors = data.get("sectors") or data.get("sector_results") or []
        summary = {
            "uid": data.get("uid"),
            "sectores": len(sectors) if isinstance(sectors, (list, dict)) else sectors,
        }
        self._fill_kv(self._dump_table, summary)

    # -- dumps guardados (artifacts/) --------------------------------------
    def set_dumps(self, names: list[str]) -> None:
        """Puebla el combo de dumps restaurables (nombres de fichero)."""
        cur = self._dumps.currentData()
        self._dumps.clear()
        for n in names:
            self._dumps.addItem(n, n)
        if not names:
            self._dumps.addItem("(sin dumps en artifacts/)", "")
        if cur:
            i = self._dumps.findData(cur)
            if i >= 0:
                self._dumps.setCurrentIndex(i)

    def reload_dumps(self) -> None:
        self.win.mifare_reload_dumps()

    def _do_restore(self) -> None:
        name = self._dumps.currentData()
        if not name:
            self.win.notify.emit("Mifare: no hay dump seleccionado.")
            return
        self.win.mifare_restore(name)
