from collections import defaultdict
import logging
import time
import urllib.parse

from pet_monitor.common import NetworkInterfaceInfo, ExtraNetworkInfoType
from pet_monitor.network_db import DBInterface
from pet_monitor.service_base import ServiceBase
from pet_monitor.settings import TPLinkSettings, get_settings
from pet_monitor.tplink_scraper.tplink_interface import TPLinkInterface

_logger = logging.getLogger(__name__)


class TPLinkScraper(ServiceBase):
    def __init__(self, settings: TPLinkSettings) -> None:
        super().__init__(settings.update_period_sec)
        self.settings = settings

    def _update(self) -> bool:
        try:
            tplink = TPLinkInterface(
                self.settings.router_ip, self.settings.username, self.settings.password)
            clients = tplink.get_dhcp_clients()
            reservations = tplink.get_dhcp_static_reservations()
            traffic = tplink.get_traffic_stats()
        except Exception as e:
            _logger.error(e)
            return False

        with DBInterface() as db_interface:
            db_interface.delete_old_traffic_stats(self.settings.update_period_sec)

            timestamp = int(time.time())
            devices: dict[str, NetworkInterfaceInfo] = {}
            extra_info = defaultdict(dict)
            for entry in reservations:
                mac = entry['mac']
                devices[mac] = NetworkInterfaceInfo(
                    timestamp=timestamp,
                    mac=mac,
                    ip=entry['ip']
                )
                extra_info[mac][ExtraNetworkInfoType.ROUTER_DESCRIPTION] = urllib.parse.unquote(entry['note'])
            for entry in clients:
                mac = entry['macaddr']
                if mac not in devices:
                    devices[mac] = NetworkInterfaceInfo(
                        timestamp=timestamp,
                        mac=mac,
                        ip=entry['ipaddr'],
                    )
                if entry['name'] != '--':
                    extra_info[mac][ExtraNetworkInfoType.DHCP_NAME] = entry['name']

            for mac, device in devices.items():
                db_interface.add_network_info(device, extra_info=extra_info[mac])

            pet_info = db_interface.get_pet_info()
            pet_device_map = db_interface.get_network_info_for_pets(pet_info)

            for traffic_entry in traffic:
                for name, interface in pet_device_map.items():
                    if interface.ip == traffic_entry['addr']:
                        db_interface.add_traffic_for_pet(name, traffic_entry['rx_bytes'], traffic_entry['tx_bytes'], timestamp)

            _logger.debug(
                f'Scrape Succeeded: reservations={len(reservations)}, clients={len(clients)}, traffic={len(traffic)}')
            return True


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    settings = get_settings()
    if settings.tplink_settings is None:
        print("TPLink settings not found.")
        return

    DBInterface.set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)
    tplink = TPLinkScraper(settings.tplink_settings)
    ServiceBase.run_services([tplink])


if __name__ == '__main__':
    main()
