import logging
import threading
from typing import NamedTuple, Optional

from zeroconf import (IPVersion, ServiceBrowser, ServiceListener, Zeroconf,
                      ZeroconfServiceTypes)

from pet_monitor.common import (TRACE, ExtraNetworkInfoType,
                                NetworkInterfaceInfo, get_mac_for_ip_address,
                                standardize_mac_address)
from pet_monitor.network_db import DBInterface
from pet_monitor.service_base import ServiceBase
from pet_monitor.settings import MDNSSettings, get_settings

_logger = logging.getLogger(__name__)


class MDNSDevice(NamedTuple):
    host: str
    name: str
    ip: str
    services: set[str]
    mac: Optional[str]


class MyListener(ServiceListener):
    def __init__(self) -> None:
        self.data_lock = threading.Lock()
        self.entries: dict[str, MDNSDevice] = {}

    def _handle_service(self, zc: Zeroconf, type_: str, name: str):
        info = zc.get_service_info(type_, name)
        if info is None:
            return
        if info.server is None:
            return
        addresses = info.ip_addresses_by_version(IPVersion.V4Only)
        if len(addresses) == 0:
            return

        diplay_name = info.get_name()
        diplay_service = type_.split('.')[0]
        ip = addresses[0]
        mdns_host = info.server
        diplay_service = diplay_service[1:] if diplay_service[0] == '_' else diplay_service

        with self.data_lock:
            mac = self.entries[mdns_host].mac if mdns_host in self.entries else None
        if mac is None:
            # Some devices report mac addresses, but this is more reliable on same LAN.
            if b'mac' in info.properties and info.properties[b'mac']:
                mac = standardize_mac_address(info.properties[b'mac'].decode())
            else:
                mac = get_mac_for_ip_address(ip)
                if mac:
                    mac = standardize_mac_address(mac)

        with self.data_lock:
            if mdns_host in self.entries:
                entry = self.entries[mdns_host]
                services = entry.services.union(set([diplay_service]))
                # Some devices use a different name for each service.
                if entry.name != diplay_name:
                    diplay_name = mdns_host.split('.')[0]
            else:
                services = set([diplay_service])

            self.entries[mdns_host] = MDNSDevice(
                host=mdns_host,
                name=diplay_name,
                ip=str(ip),
                mac=mac,
                services=services
            )

            # _logger.info(self.entries[mdns_host])

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self._handle_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self._handle_service(zc, type_, name)


class MDNSScraper(ServiceBase):
    def __init__(self, settings: MDNSSettings) -> None:
        super().__init__(settings.time_between_updates)
        self.settings = settings
        zeroconf = Zeroconf()
        services = list(ZeroconfServiceTypes.find(zc=zeroconf))
        self.listener = MyListener()
        self.browser = ServiceBrowser(zeroconf, services, self.listener)

    def _update(self) -> None:
        with self.listener.data_lock:
            with DBInterface() as db_interface:
                for entry in self.listener.entries.values():
                    extra_info = {
                        ExtraNetworkInfoType.MDNS_NAME: entry.name,
                        ExtraNetworkInfoType.MDNS_SERVICES: ','.join(entry.services)
                    }
                    device = NetworkInterfaceInfo(
                        mac=entry.mac,
                        ip=entry.ip,
                        mdns_hostname=entry.host
                    )
                    db_interface.add_network_info(device, extra_info=extra_info)
                    _logger.log(TRACE, entry)

            _logger.debug(f'mDNS found {len(self.listener.entries)} clients.')
            self.listener.entries = {}


def main():
    logging.basicConfig(level=TRACE, format='%(asctime)s - %(levelname)s - %(message)s')

    settings = get_settings()
    if settings.mdns_settings is None:
        print("MDNS settings not found.")
        return

    DBInterface.set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)
    mdns = MDNSScraper(settings.mdns_settings)
    ServiceBase.run_services([mdns])


if __name__ == '__main__':
    main()
