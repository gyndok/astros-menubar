import queue
import threading

from sportsbar.worker import BackgroundWorker


class MainLoop:
    """Stand-in for the AppKit main run loop: jobs dispatched to it run
    only when the test pumps it, on the test's own thread."""

    def __init__(self):
        self.q = queue.Queue()

    def dispatch(self, fn, *args):
        self.q.put((fn, args))

    def pump(self, n=1, timeout=5):
        for _ in range(n):
            fn, args = self.q.get(timeout=timeout)
            fn(*args)


def test_work_runs_off_main_thread_and_on_done_on_main():
    loop = MainLoop()
    worker = BackgroundWorker(loop.dispatch)
    seen = {}
    worker.submit(
        "job",
        lambda: seen.__setitem__("work", threading.current_thread()),
        lambda: seen.__setitem__("done", threading.current_thread()),
    )
    loop.pump()
    worker.stop(timeout=5)
    assert seen["work"] is not threading.main_thread()
    assert seen["done"] is threading.current_thread()


def test_duplicate_pending_jobs_are_dropped():
    loop = MainLoop()
    worker = BackgroundWorker(loop.dispatch)
    gate = threading.Event()
    runs = []
    assert worker.submit("slow", lambda: (gate.wait(5), runs.append(1)))
    assert not worker.submit("slow", lambda: runs.append(2))  # still pending
    assert worker.submit("other", lambda: runs.append(3))
    gate.set()
    worker.stop(timeout=5)
    assert runs == [1, 3]
    # Once finished, the same name can be submitted again
    worker = BackgroundWorker(loop.dispatch)
    assert worker.submit("slow", lambda: runs.append(4))
    worker.stop(timeout=5)
    assert runs == [1, 3, 4]


def test_failing_work_still_calls_on_done_and_worker_survives():
    loop = MainLoop()
    worker = BackgroundWorker(loop.dispatch)
    done = []
    worker.submit("bad", lambda: 1 / 0, lambda: done.append("bad"))
    loop.pump()
    worker.submit("good", lambda: None, lambda: done.append("good"))
    loop.pump()
    worker.stop(timeout=5)
    assert done == ["bad", "good"]


def test_next_job_waits_for_previous_on_done():
    loop = MainLoop()
    worker = BackgroundWorker(loop.dispatch)
    events = []
    worker.submit("a", lambda: events.append("work a"), lambda: events.append("done a"))
    worker.submit("b", lambda: events.append("work b"))
    # Job b must not start while a's on_done is still waiting for the main loop
    threading.Event().wait(0.2)
    assert events == ["work a"]
    loop.pump()
    worker.stop(timeout=5)
    assert events == ["work a", "done a", "work b"]
