"""Background tasks, one at a time: the hh browser profile can't be opened twice."""
import threading
import time
import traceback
from collections.abc import Callable

from kolenke.db.repositories.events import log


class JobRunner:
    def __init__(self):
        self.name: str | None = None
        self.stop_requested = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()  # two clicks at once must not start two browsers

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, name: str, fn: Callable[[], object]) -> bool:
        """False when another task is still running."""
        with self._lock:
            if self.running:
                return False
            self.name, self.stop_requested = name, False
            self._thread = threading.Thread(target=self._run, args=(name, fn), daemon=True)
            self._thread.start()
            return True

    @staticmethod
    def _run(name: str, fn: Callable[[], object]) -> None:
        try:
            fn()
        except Exception as e:
            log(f"Ошибка в задаче «{name}»: {e}")
            traceback.print_exc()

    def stop(self) -> None:
        self.stop_requested = True

    def sleep(self, seconds: float) -> None:
        """A pause that ends early when you press «Стоп»."""
        end = time.monotonic() + seconds
        while not self.stop_requested and time.monotonic() < end:
            time.sleep(min(1, end - time.monotonic()))


runner = JobRunner()
