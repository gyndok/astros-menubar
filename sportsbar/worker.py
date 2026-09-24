"""Background worker: keeps network I/O off the main (UI) thread.

rumps timers and menu callbacks run on the main run loop, so a slow API
call made there freezes the whole menu. Jobs submitted here run one at a
time on a single worker thread; each job's optional `on_done` callback is
handed back to the main thread (via `dispatch_main`) to update the UI.

The worker waits for `on_done` to finish before starting the next job, so
app state is never mutated by a job while the main thread is reading it
to rebuild menus.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Optional, Set

Job = Callable[[], None]


class BackgroundWorker:
    def __init__(self, dispatch_main: Callable[[Job], None]) -> None:
        self._dispatch_main = dispatch_main
        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._pending: Set[str] = set()
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name="sportsbar-worker", daemon=True
        )
        self._thread.start()

    def submit(self, name: str, work: Job, on_done: Optional[Job] = None) -> bool:
        """Queue `work` for the worker thread, then `on_done` on the main thread.

        A job whose name is already queued, running, or updating the UI is
        dropped (returns False) — a timer tick that fires while the previous tick is still
        waiting on a slow API shouldn't pile up duplicate requests.
        """
        with self._lock:
            if name in self._pending:
                logging.info("background job %s already pending — skipped", name)
                return False
            self._pending.add(name)
        self._queue.put((name, work, on_done))
        return True

    def idle(self) -> bool:
        """True when no job is queued, running, or waiting on its UI update."""
        with self._lock:
            return not self._pending

    def stop(self, timeout: Optional[float] = None) -> None:
        """Finish queued jobs, then end the worker thread."""
        self._queue.put(None)
        self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            name, work, on_done = item
            try:
                work()
            except Exception as exc:
                logging.exception("background job %s failed: %s", name, exc)
            if on_done is not None:
                self._run_on_main(name, on_done)
            # Still "pending" until its UI update is done, so a tick that
            # fires mid-update doesn't queue a duplicate.
            with self._lock:
                self._pending.discard(name)

    def _run_on_main(self, name: str, on_done: Job) -> None:
        done = threading.Event()

        def finish() -> None:
            try:
                on_done()
            except Exception as exc:
                logging.exception("on_done for %s failed: %s", name, exc)
            finally:
                done.set()

        self._dispatch_main(finish)
        # Bounded so a wedged main thread can't stop refreshes forever.
        if not done.wait(timeout=60):
            logging.warning("on_done for %s still pending after 60s", name)
