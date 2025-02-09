import logging
import time
import urllib.parse

from pet_monitor.common import NetworkInterfaceInfo
from pet_monitor.network_db import (
    add_network_info,
    add_traffic_for_pet,
    delete_old_traffic_stats,
    get_db_connection,
    get_network_info_for_pets,
    get_pet_info,
    set_hard_coded_pet_interfaces,
)
from pet_monitor.service_base import Condition, ServiceBase, run_services
from pet_monitor.settings import TPLinkSettings, get_settings
from pet_monitor.tplink_scraper.tplink_interface import TPLinkInterface

_logger = logging.getLogger(__name__)


class TPLinkScraper(ServiceBase):
    def __init__(self, stop_condition: Condition, settings: TPLinkSettings) -> None:
        super().__init__(settings.update_period_sec, stop_condition)
        self.settings = settings

    def _update(self) -> bool:
        conn = get_db_connection()
        delete_old_traffic_stats(conn, self.settings.update_period_sec)

        try:
            tplink = TPLinkInterface(
                self.settings.router_ip, self.settings.username, self.settings.password)
            clients = tplink.get_dhcp_clients()
            reservations = tplink.get_dhcp_static_reservations()
            traffic = tplink.get_traffic_stats()
        except Exception as e:
            _logger.error(e)
            return False

        timestamp = int(time.time())
        devices: dict[str, NetworkInterfaceInfo] = {}
        for entry in reservations:
            mac = entry['mac']
            devices[mac] = NetworkInterfaceInfo(
                timestamp=timestamp,
                mac=mac,
                ip=entry['ip']
            ).replace_description({
                'router_description': urllib.parse.unquote(entry['note'])
            })
        for entry in clients:
            mac = entry['macaddr']
            if mac in devices:
                device = devices[mac]
            else:
                device = NetworkInterfaceInfo(
                    timestamp=timestamp,
                    mac=mac,
                    ip=entry['ipaddr'],
                )
            if entry['name'] != '--':
                device = device.replace_description_field('dhcp_name', entry['name'])
            devices[mac] = device

        for device in devices.values():
            add_network_info(conn, device)

        pet_info = get_pet_info(conn)
        pet_device_map = get_network_info_for_pets(conn, pet_info)

        for traffic_entry in traffic:
            for name, interface in pet_device_map.items():
                if interface.ip == traffic_entry['addr']:
                    add_traffic_for_pet(conn, name, traffic_entry['rx_bytes'], traffic_entry['tx_bytes'], timestamp)

        _logger.debug(
            f'Scrape Succeeded: reservations={
                len(reservations)}, clients={
                len(clients)}, traffic={
                len(traffic)}')
        return True


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    settings = get_settings()
    if settings.tplink_settings is None:
        print("TPLink settings not found.")
        return

    set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)
    stop_condition = Condition()
    tplink = TPLinkScraper(stop_condition, settings.tplink_settings)
    run_services(stop_condition, [tplink])


if __name__ == '__main__':
    main()
