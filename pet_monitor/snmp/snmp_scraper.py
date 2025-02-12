import logging
import time

from pet_monitor.common import NetworkInterfaceInfo
from pet_monitor.network_db import DBInterface
from pet_monitor.service_base import ServiceBase
from pet_monitor.settings import SNMPSettings, get_settings
from pet_monitor.snmp.get_device_stats import get_attached_ips

_logger = logging.getLogger(__name__)


class SNMPScraper(ServiceBase):
    def __init__(self, settings: SNMPSettings) -> None:
        super().__init__(settings.time_between_scans)
        self.settings = settings

    def _update(self) -> bool:
        try:
            devices = get_attached_ips(self.settings.router_ip, self.settings.community)
        except Exception as e:
            _logger.error(e)
            return False

        timestamp = int(time.time())
        with DBInterface() as db_interface:
            for device in devices:
                db_interface.add_network_info(NetworkInterfaceInfo(
                    timestamp=timestamp,
                    ip=device[0],
                    mac=device[1],
                ))

            _logger.debug(
                f'Router SNMP found had {len(devices)} clients.')
            return True


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    settings = get_settings()
    if settings.snmp_settings is None:
        print("SNMP settings not found.")
        return

    DBInterface.set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)
    snmp = SNMPScraper(settings.snmp_settings)
    ServiceBase.run_services([snmp])


if __name__ == '__main__':
    main()
