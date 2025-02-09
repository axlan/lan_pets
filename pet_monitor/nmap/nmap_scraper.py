import logging
import time
from threading import Condition

from nmap import PortScannerHostDict

from pet_monitor.common import NetworkInterfaceInfo
from pet_monitor.network_db import (
    add_network_info,
    get_db_connection,
    set_hard_coded_pet_interfaces,
)
from pet_monitor.nmap.nmap_interface import NMAPRunner
from pet_monitor.service_base import ServiceBase, run_services
from pet_monitor.settings import NMAPSettings, get_settings

_logger = logging.getLogger(__name__)


class NMAPScraper(ServiceBase):
    def __init__(self, stop_condition: Condition, settings: NMAPSettings) -> None:
        super().__init__(settings.time_between_scans, stop_condition)
        self.settings = settings
        self.nmap_interface = NMAPRunner(settings)

    def _check(self):
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
            conn = get_db_connection()
            if 'nmap' in self.nmap_interface.result:
                _logger.debug(self.nmap_interface.result['nmap'])

            if 'scan' in self.nmap_interface.result:
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

                    add_network_info(conn, NetworkInterfaceInfo(
                        timestamp=timestamp,
                        ip=ip,
                        mac=mac,
                        dns_hostname=host_name
                    ))

            self.nmap_interface.result = None

    def _update(self):
        if self.nmap_interface.in_progress:
            _logger.error('Attemtping new scan while previous run has not completed.')
            return

        self.nmap_interface.scan_ranges()


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    settings = get_settings()
    if settings.nmap_settings is None:
        print("NMAP settings not found.")
        return

    set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)
    stop_condition = Condition()
    nmap = NMAPScraper(stop_condition, settings.nmap_settings)
    run_services(stop_condition, [nmap])


if __name__ == '__main__':
    main()
