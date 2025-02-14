import logging
import time

from pet_monitor.common import CPUStats, NetworkInterfaceInfo
from pet_monitor.network_db import DBInterface
from pet_monitor.service_base import ServiceBase
from pet_monitor.settings import SNMPSettings, get_settings
from pet_monitor.snmp.get_device_stats import get_attached_ips, get_cpu_idle_percent, get_ram_info

_logger = logging.getLogger(__name__)


class SNMPScraper(ServiceBase):
    def __init__(self, settings: SNMPSettings) -> None:
        super().__init__(settings.time_between_scans)
        self.settings = settings

    def _update(self):
        try:
            devices = get_attached_ips(self.settings.router_ip, self.settings.community)
        except Exception as e:
            _logger.error(e)
            return False
        
        _logger.debug(f'Router SNMP found had {len(devices)} clients.')

        with DBInterface() as db_interface:
            # Clear old data.
            db_interface.delete_old_cpu_stats(int(self.settings.history_len))

            pet_info = db_interface.get_pet_info()
            pet_device_map = db_interface.get_network_info_for_pets(pet_info)

        cpu_stats: dict[str, CPUStats] = {}
        for name, device in pet_device_map.items():
            host = device.get_host()
            if host:
                print(host, self.settings.community)
                cpu_idle = get_cpu_idle_percent(host, self.settings.community)
                if cpu_idle is None:
                    continue
                mem_usage = get_ram_info(host, self.settings.community)
                if mem_usage is not None:
                    mem_usage_percent = float(mem_usage[0]) / float(mem_usage[1])
                    cpu_stats[name] = CPUStats(100 - cpu_idle, mem_usage_percent, int(time.time()))

        _logger.debug(f'SNMP found {len(cpu_stats)} devices with cpu stats.')

        timestamp = int(time.time())
        with DBInterface() as db_interface:
            for device in devices:
                db_interface.add_network_info(NetworkInterfaceInfo(
                    timestamp=timestamp,
                    ip=device[0],
                    mac=device[1],
                ))

            for name, stats in cpu_stats.items():
                db_interface.add_cpu_stats_for_pet(name, stats)


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
