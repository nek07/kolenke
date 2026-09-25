"""Background loop: reminders before planned steps and the autopilot schedule. Started and stopped by the app lifespan."""
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from kolenke.db.repositories import settings
from kolenke.db.repositories.events import log
from kolenke.services import pipeline
from kolenke.services.notify import notify
from kolenke.workers.runner import runner

TICK_SECONDS = 20


@dataclass
class State:
    last_run: datetime | None = None
    next_run: datetime | None = None


state = State()
_stop = threading.Event()
_thread: threading.Thread | None = None


def tick(now: datetime | None = None) -> None:
    """One pass of the loop; separate so it can be tested without waiting."""
    from kolenke.workers.autopilot import cycle  # the autopilot pulls in the browser code: import it only when needed

    now = now or datetime.now()
    try:
        pipeline.notify_due(notify)
    except Exception as e:
        log(f"Напоминания: ошибка {e}")
    try:
        s = settings.get()
        if not s.autopilot_on:
            state.next_run = None
            return
        if not s.autopilot_from <= now.hour < s.autopilot_to:
            return
        if (state.next_run and now < state.next_run) or runner.running:
            return
        if runner.start("Автопилот", cycle):
            log("▶ Автопилот")
            state.last_run = now
            state.next_run = now + timedelta(minutes=s.autopilot_interval)
    except Exception as e:
        log(f"Автопилот: ошибка планировщика {e}")


def _loop() -> None:
    while not _stop.wait(TICK_SECONDS):
        tick()


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    runner.stop()  # a running task ends at its next checkpoint
