"""Run blocking work off the GUI thread; results and progress come back on the GUI thread."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

_alive: set["Job"] = set()


class _Signals(QObject):
    done = Signal(object)
    error = Signal(object)
    progress = Signal(str, int, int)


class Job(QRunnable):
    def __init__(self, fn: Callable[..., Any], args: tuple):
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.args = fn, args
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args, self.signals.progress.emit)
        except BaseException as e:  # noqa: BLE001 - surfaced to the UI
            e.__traceback_text__ = traceback.format_exc()
            self.signals.error.emit(e)
        else:
            self.signals.done.emit(result)


def run(fn: Callable[..., Any], *args, on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[str, int, int], None] | None = None) -> Job:
    """`fn(*args, progress)` runs on a worker thread; `progress(text, cur, max)` is thread-safe."""
    job = Job(fn, args)
    _alive.add(job)

    def finish(cb, value):
        _alive.discard(job)
        if cb:
            cb(value)

    job.signals.done.connect(lambda r: finish(on_done, r))
    job.signals.error.connect(lambda e: finish(on_error, e))
    if on_progress:
        job.signals.progress.connect(on_progress)
    QThreadPool.globalInstance().start(job)
    return job
