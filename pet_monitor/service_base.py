import logging
import random
import time
from threading import Condition, Thread
from typing import Optional

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
    error_condition = Condition()

    def __init__(self, update_period_sec: float) -> None:
        self._rate_limiter = RateLimiter(update_period_sec)
        self.is_running = False
        self.thread: Optional[Thread] = None

    def run(self) -> None:
        if not self.is_running:
            self.is_running = True
            self.thread = Thread(target=self._run_loop)
            self.thread.start()

    def _run_loop(self) -> None:
        try:
            while self.is_running:
                self._check()
                if not self._rate_limiter.get_ready():
                    time.sleep(0.1)
                    continue
                self._update()
        except Exception:
            _logger.error('Unhandled Exception:', exc_info=True)
        with self.error_condition:
            self.error_condition.notify()

    def _check(self) -> None:
        pass

    def _update(self) -> None:
        pass

    def stop(self):
        if self.is_running and self.thread:
            self.is_running = False
            self.thread.join()

    @classmethod
    def run_services(cls, services: list['ServiceBase']):
        try:
            with cls.error_condition:
                for service in services:
                    service.run()
                    # Add random startup delay to offset services.
                    time.sleep(random.uniform(1, 2))
                cls.error_condition.wait()
        except KeyboardInterrupt:
            pass

        _logger.info('Stopping services.')
        for service in services:
            service.stop()
