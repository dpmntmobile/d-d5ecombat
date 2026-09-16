"""Background Qt worker used to execute simulation sections."""

import traceback

from PySide6.QtCore import QObject, Signal, Slot

from .gui_service import SimulationCancelled, run_simulations


class SimulationWorker(QObject):
    succeeded = Signal(object)
    cancelled = Signal()
    failed = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal()

    def __init__(self, build, monster, settings, sections):
        super().__init__()
        self.build = build
        self.monster = monster
        self.settings = settings
        self.sections = sections
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    @Slot()
    def run(self):
        try:
            result = run_simulations(
                self.build,
                self.monster,
                self.settings,
                sections=self.sections,
                progress_callback=self.progress.emit,
                is_cancelled=lambda: self._cancel_requested,
            )
        except SimulationCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()
