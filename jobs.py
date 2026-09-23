"""One background task at a time (the browser profile can't be opened twice)."""
import threading
import traceback

import db


class Job:
    def __init__(self):
        self.name = None
        self.stop_requested = False
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, name, fn):
        if self.running:
            return False
        self.name, self.stop_requested = name, False

        def run():
            try:
                fn()
            except Exception as e:
                db.log(f"Ошибка в задаче «{name}»: {e}")
                traceback.print_exc()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.stop_requested = True


job = Job()
