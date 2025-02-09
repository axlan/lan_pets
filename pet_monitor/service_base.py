import logging
import time
from typing import Optional

from threading import Condition, Thread

_logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, update_period_sec) -> None:
        self.update_period_sec = update_period_sec
        self.last_update = float('-inf')

    def get_ready(self) -> bool:
        if not self.is_ready():
            return False
        else:
            self.last_update = time.monotonic()
            return True

    def is_ready(self) -> bool:
        return time.monotonic() - self.last_update > self.update_period_sec


class ServiceBase:
    def __init__(self, update_period_sec: float, stop_condition: Condition) -> None:
        self.rate_limiter = RateLimiter(update_period_sec)
        self.is_running = False
        self.stop_condition = stop_condition
        self.thread: Optional[Thread] = None

    def run(self) -> None:
        if not self.is_running:
            self.is_running = True
            self.thread = Thread(target=self._run_loop)
            self.thread.start()

    def _run_loop(self) -> None:
            try:
                while self.is_running:
                    if not self.rate_limiter.get_ready():
                        time.sleep(0.1)
                        continue
                    self._update()
            except Exception:
                _logger.error('Unhandled Exception:', exc_info=True)
            with self.stop_condition:
                self.stop_condition.notify()

    def _update(self) -> None:
        pass

    def stop(self):
        if self.is_running and self.thread:
            self.is_running = False
            self.thread.join()


def run_services(stop_condition: Condition, services: list[ServiceBase]):
    try:
        with stop_condition:
            for service in services:
                service.run()
            stop_condition.wait()
    except KeyboardInterrupt:
        pass

    _logger.info('Stopping services.')
    for service in services:
        service.stop()
