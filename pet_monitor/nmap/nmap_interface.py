
import logging
import time
from threading import Thread
from typing import Any, Optional

import nmap

from pet_monitor.settings import NMAPSettings

_logger = logging.getLogger(__name__)


class NMAPRunner:
    '''
    This class leverages the python-nmap library to interact with the nmap process. This is mostly to handle parsing the
    XML output. It specifically does not use the PortScannerAsync class to call nmap asynchronously do to the way that
    class spawns a seperate process for each host being scanned which is better handled by a single nmap process.
    '''
    def __init__(self, settings: NMAPSettings) -> None:
        self.settings = settings
        self.in_progress = False
        self.nm = nmap.PortScanner()
        self.result: Optional[dict[str, Any]] = None

    def _run_nmap_thread(self, hosts="127.0.0.1", ports=None, arguments="-sV"):
        try:
            self.result = self.nm.scan(hosts, ports, arguments, sudo=self.settings.use_sudo)  # type: ignore
        except Exception as e:
            _logger.error(e)
            self.result = None

        self.in_progress = False

    def _run_nmap(self, hosts="127.0.0.1", ports=None, arguments="-sV"):
        self.in_progress = True
        thread = Thread(target=NMAPRunner._run_nmap_thread, name='nmap_runner', args=(self, hosts, ports, arguments))
        thread.start()

    def scan_ranges(self):
        self._run_nmap(self.settings.ip_ranges, arguments="-sn")


def _main():
    runner = NMAPRunner(NMAPSettings())
    runner.scan_ranges()
    while runner.in_progress:
        time.sleep(0.1)
        if not runner.in_progress:
            print(runner.result)


if __name__ == "__main__":
    _main()
