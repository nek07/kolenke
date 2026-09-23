"""One background task at a time (the browser profile can't be opened twice)."""
import threading
import traceback

import db


class Job:
    def __init__(self):
        self.name = None
        self.stop_requested = False
        self._thread = None
        self._lock = threading.Lock()  # two clicks at once must not start two browsers

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, name, fn):
        with self._lock:
            if self.running:
                return False
            self.name, self.stop_requested = name, False
            self._thread = threading.Thread(target=self._run, args=(name, fn), daemon=True)
            self._thread.start()
            return True

    @staticmethod
    def _run(name, fn):
        try:
            fn()
        except Exception as e:
            db.log(f"Ошибка в задаче «{name}»: {e}")
            traceback.print_exc()

    def stop(self):
        self.stop_requested = True


job = Job()
