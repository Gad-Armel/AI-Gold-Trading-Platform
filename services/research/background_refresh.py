"""Bounded public-data refreshes that never block the position-management loop."""
from concurrent.futures import ThreadPoolExecutor
import time


class BackgroundRefresh:
    def __init__(self, workers=3):
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='gold-data')
        self.jobs = {}
        self.values = {}
        self.errors = {}
        self.started = {}

    def poll(self, name, interval, fetch, default=None):
        future = self.jobs.get(name)
        if future is not None and future.done():
            try:
                self.values[name] = future.result()
                self.errors.pop(name, None)
            except Exception as error:
                # Provider implementations should redact credentials in errors.
                self.errors[name] = type(error).__name__
            del self.jobs[name]
        now = time.monotonic()
        if name not in self.jobs and now-self.started.get(name, -float('inf')) >= interval:
            self.started[name] = now
            self.jobs[name] = self.executor.submit(fetch)
        return self.values.get(name, default)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
