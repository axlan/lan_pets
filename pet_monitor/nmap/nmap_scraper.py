import logging
import time

from nmap import PortScannerHostDict

from pet_monitor.common import NetworkInterfaceInfo, TRACE, ExtraNetworkInfoType
from pet_monitor.network_db import DBInterface
from pet_monitor.nmap.nmap_interface import NMAPRunner
from pet_monitor.service_base import ServiceBase
from pet_monitor.settings import NMAPSettings, get_settings

_logger = logging.getLogger(__name__)


class NMAPScraper(ServiceBase):
    def __init__(self, settings: NMAPSettings) -> None:
        super().__init__(settings.time_between_scans)
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
            with DBInterface() as db_interface:
                _logger.log(TRACE, self.nmap_interface.result)
                if 'nmap' in self.nmap_interface.result:
                    info = self.nmap_interface.result['nmap']
                    if 'command_line' in info and 'scanstats' in info:
                        _logger.debug(f'"{info["command_line"]}": {info["scanstats"]}')


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

                        services = []
                        if 'tcp' in result:
                            for port, status in result['tcp'].items():
                                if status['state'] == 'open':
                                    services.append(f'{port}({status['name']})')
                        extra_info = {} if len(services) == 0 else {ExtraNetworkInfoType.NMAP_SERVICES: ','.join(services)}

                        db_interface.add_network_info(NetworkInterfaceInfo(
                            timestamp=timestamp,
                            ip=ip,
                            mac=mac,
                            dns_hostname=host_name
                        ), extra_info=extra_info)

            self.nmap_interface.result = None

    def _update(self):
        if self.nmap_interface.in_progress:
            _logger.error('Attempting new scan while previous run has not completed.')
            return

        self.nmap_interface.scan_ranges(self.settings.nmap_flags)


def main():
    logging.basicConfig(level=TRACE, format='%(asctime)s - %(levelname)s - %(message)s')

    settings = get_settings()
    if settings.nmap_settings is None:
        print("NMAP settings not found.")
        return

    DBInterface.set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)
    nmap = NMAPScraper(settings.nmap_settings)
    ServiceBase.run_services([nmap])


if __name__ == '__main__':
    main()
