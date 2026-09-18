"""Ejecución de trabajo de hardware/red fuera del hilo de la GUI (Qt).

Las operaciones que bloquean (conectar lector, capturar tarjeta, emular NDEF…)
corren en un `QThreadPool`; el resultado y el progreso vuelven al hilo de la GUI
por señales Qt (conexión en cola, thread-safe). Nunca tocar widgets desde el
hilo de trabajo — solo emitir señales.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)  # valor de retorno de la función
    error = Signal(str)  # mensaje de excepción
    line = Signal(str)  # progreso/streaming (una línea)
    finished = Signal()


# Mantiene vivos los workers en curso: sin esto, el `QThreadPool` auto-borra el
# `QRunnable` (y su `WorkerSignals`) al terminar `run()`, y las señales
# `result`/`error` que quedaron **en cola** hacia el hilo GUI se pierden antes
# de procesarse → los callbacks (`on_result`/`on_error`) nunca corren. Se
# descarta el worker al procesarse `finished` (que se emite después de
# result/error), ya con los callbacks entregados.
_ACTIVE: set["Worker"] = set()


class Worker(QRunnable):
    """Corre `fn(*args, **kwargs)` en el pool. Si `fn` acepta un parámetro
    `progress`, se le inyecta un callable que emite `signals.line`."""

    def __init__(self, fn: Callable, *args, want_progress: bool = False, **kwargs):
        super().__init__()
        self.setAutoDelete(False)  # la vida la gestiona Python (_ACTIVE), no el pool
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._want_progress = want_progress
        self.signals = WorkerSignals()

    def _emit(self, signal, *args) -> None:
        """Emite una señal de forma defensiva. Si la GUI se está cerrando, Qt ya
        destruyó el `WorkerSignals` (C++) mientras el worker seguía en el pool →
        `emit` lanza `RuntimeError: Signal source has been deleted`. No es un
        error real (la ventana se fue): lo tragamos en vez de reventar el
        override de QRunnable::run() con un traceback en cascada."""
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    @Slot()
    def run(self) -> None:
        progress = self._emit_line if self._want_progress else None
        try:
            if self._want_progress:
                self._kwargs["progress"] = progress
            res = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # noqa: BLE001 — se reporta al hilo GUI
            self._emit(self.signals.error, str(e))
        else:
            self._emit(self.signals.result, res)
        finally:
            self._emit(self.signals.finished)

    def _emit_line(self, line) -> None:
        self._emit(self.signals.line, line)


def submit(
    pool,
    fn,
    *args,
    on_result=None,
    on_error=None,
    on_line=None,
    on_finished=None,
    want_progress=False,
    **kwargs,
) -> Worker:
    w = Worker(fn, *args, want_progress=want_progress, **kwargs)
    _ACTIVE.add(w)  # lo mantiene vivo hasta 'finished'
    if on_result:
        w.signals.result.connect(on_result)
    if on_error:
        w.signals.error.connect(on_error)
    if on_line:
        w.signals.line.connect(on_line)
    if on_finished:
        w.signals.finished.connect(on_finished)
    w.signals.finished.connect(lambda: _ACTIVE.discard(w))
    pool.start(w)
    return w
