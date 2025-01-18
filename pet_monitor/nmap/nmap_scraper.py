import io
import logging
import time
import urllib.parse
from sqlite3 import IntegrityError
from collections import defaultdict
from typing import NamedTuple, Optional

from nmap import PortScannerHostDict

from pet_monitor.common import (DATA_DIR, ClientInfo, TrafficStats,
                                get_db_connection)
from pet_monitor.settings import RateLimiter, NMAPSettings, get_settings
from pet_monitor.nmap.nmap_interface import NMAPRunner

_logger = logging.getLogger(__name__)


SCHEMA_SQL = '''\
CREATE TABLE nmap_results (
    row_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,     -- Unix time of observation
    ip VARCHAR(15) NOT NULL,       -- IP address (format: IPv4).
    mac VARCHAR(17),               -- MAC address (format: XX-XX-XX-XX-XX-XX). NULL if not available.
    host_name VARCHAR(255),        -- Name of the client. NULL if not available.
    UNIQUE (mac),                            -- Ensure MAC addresses are unique
    UNIQUE (ip),                            -- Ensure IP addresses are unique
    UNIQUE (host_name),         -- Ensure host names addresses are unique
    PRIMARY KEY(row_id)
);
'''


class NMAPResult(NamedTuple):
    timestamp: int
    ip: str
    mac: Optional[str] = None
    host_name: Optional[str] = None


class NMAPScraper():
    def __init__(self, settings: NMAPSettings) -> None:
        self.settings = settings
        self.nmap_interface = NMAPRunner(settings)
        self.rate_limiter = RateLimiter(settings.time_between_scans)
        self.conn = get_db_connection(DATA_DIR / 'nmap.sqlite3', SCHEMA_SQL)

    def get_all_results(self) -> set[NMAPResult]:
        cur = self.conn.cursor()
        cur.execute("SELECT timestamp, ip, mac, host_name FROM nmap_results;""")
        return {NMAPResult(*r) for r in cur.fetchall()}

    def _check_for_scan_complete(self):
        #     {'nmap': {'command_line': 'nmap -oX - -sn 192.168.1.100-255',
        #       'scaninfo': {},
        #       'scanstats': {'timestr': 'Wed Jan  8 06:05:19 2025',
        #                     'elapsed': '4.41',
        #                     'uphosts': '23',
        #                     'downhosts': '133',
        #                     'totalhosts': '156'}},
        # 'scan': {'192.168.1.100': {'hostnames': [{'name': '',
        #                                           'type': ''}],
        #                            'addresses': {'ipv4': '192.168.1.100',
        #                                          'mac': 'A4:77:33:75:BC:C0'},
        #                            'vendor': {'A4:77:33:75:BC:C0': 'Google'},
        #                            'status': {'state': 'up',
        #                                       'reason': 'arp-response'}},
        #          '192.168.1.110': {'hostnames': [{'name': 'bee.internal',
        #                                           'type': 'PTR'}],
        #                            'addresses': {'ipv4': '192.168.1.110',
        #                                          'mac': '7C:83:34:BE:62:5C'},
        #                            'vendor': {},
        #                            'status': {'state': 'up',
        #                                       'reason': 'arp-response'}},
        if self.nmap_interface.result is not None:
            if 'nmap' in self.nmap_interface.result:
                _logger.debug(self.nmap_interface.result['nmap'])

            if 'scan' in self.nmap_interface.result:
                cur_results = self.get_all_results()
                scan: PortScannerHostDict = self.nmap_interface.result['scan']  # type: ignore
                timestamp = int(time.time())
                for ip, result in scan.items():
                    mac = None
                    host_name = None
                    if 'addresses' in result and 'mac' in result['addresses'] and len(result['addresses']['mac']) > 0:
                        mac = result['addresses']['mac'].replace(':', '-')

                    if 'hostnames' in result:
                        host_names = result['hostnames']
                        if len(host_names) > 0:
                            if len(host_names) > 1:
                                names = [n['name'] for n in host_names]
                                _logger.warning(f'Mutiple host names found for {ip}: {names}')
                            name = host_names[0]['name']
                            if len(name) > 0:
                                host_name = name

                    result = NMAPResult(timestamp, ip, mac, host_name)

                    matches = 0
                    for cur_result in cur_results:
                        if cur_result.ip == result.ip:
                            matches += 1
                        elif result.mac is not None and cur_result.mac == result.mac:
                            matches += 1
                        elif result.host_name is not None and cur_result.host_name == result.host_name:
                            matches += 1

                    cur = self.conn.cursor()

                    # Mutliple partial matches (DHCP or DNS reasigned). Delete all but one entry.
                    if matches > 1:
                        cur.execute('DELETE FROM nmap_results WHERE ip=? OR mac=? OR host_name=? LIMIT ?;',
                                    result[1:] + (matches - 1,))
                        matches = 1

                    # INSERT
                    if matches == 0:
                        # Apperently this can sometimes fail with duplicate MAC addresses in a single scan?
                        try:
                            cur.execute('INSERT INTO nmap_results(timestamp, ip, mac, host_name) VALUES (?, ?, ?, ?);', result)
                        except IntegrityError as e:
                            _logger.error(f'{e}: {result}')
                    # UPDATE
                    else:
                        cur.execute(
                            'UPDATE nmap_results SET timestamp=?, ip=?, mac=?, host_name=? WHERE ip=? OR mac=? OR host_name=? LIMIT 1;',
                            result + result[1:])

                    self.conn.commit()

            self.nmap_interface.result = None

    def is_ready(self):
        return self.rate_limiter.is_ready() or self.nmap_interface.result is not None

    def update(self):
        self._check_for_scan_complete()

        if not self.rate_limiter.get_ready():
            return

        if self.nmap_interface.in_progress:
            _logger.error('Attemtping new scan while previous run has not completed.')
            return

        self.nmap_interface.scan_ranges()


def main():
    logging.basicConfig(level=logging.DEBUG)

    settings = get_settings().nmap_settings
    if settings is None:
        print("NMAP settings not found.")
        return
    scraper = NMAPScraper(settings)

    print(scraper.get_all_results())

    try:
        while True:
            scraper.update()
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
