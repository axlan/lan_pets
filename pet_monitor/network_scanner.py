
from dataclasses import replace
from typing import Iterable

from pet_monitor.common import NetworkInterfaceInfo
from pet_monitor.settings import Settings
from pet_monitor.tplink_scraper.scraper import TPLinkScraper
from pet_monitor.nmap.nmap_scraper import NMAPScraper
from manage_pets.models import PetData


class NetworkScanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tplink_scraper = None if self.settings.tplink_settings is None else TPLinkScraper(
            self.settings.tplink_settings)
        self.nmap_scraper = None if self.settings.nmap_settings is None else NMAPScraper(self.settings.nmap_settings)

    def scan_network(self):
        # Router Scrape
        if self.tplink_scraper:
            self.tplink_scraper.update()

        # NMAP
        if self.nmap_scraper:
            self.nmap_scraper.update()

        # TODO: mDNS

    def is_ready(self):
        ready = self.tplink_scraper is not None and self.tplink_scraper.is_ready()
        ready |= self.nmap_scraper is not None and self.nmap_scraper.is_ready()

    def get_discovered_devices(self) -> set[NetworkInterfaceInfo]:
        devices: set[NetworkInterfaceInfo] = self.settings.hard_coded_interface_info
        if self.tplink_scraper:
            info = self.tplink_scraper.load_info()
            for client in info.values():
                devices.add(
                    NetworkInterfaceInfo(
                        mac=client.mac,
                        ip=client.ip,
                        dhcp_name=client.client_name,
                        router_description=client.description
                    )
                )

        if self.nmap_scraper:
            results = self.nmap_scraper.get_all_results()
            for result in results:
                # Check for duplicates.
                is_duplicate = False
                for device in devices:
                    if result.ip == device.ip or result.mac == device.mac:
                        if result.host_name is not None:
                            devices.remove(device)
                            devices.add(replace(device, dns_hostname = result.host_name))
                        is_duplicate = True
                        break

                if not is_duplicate:
                    devices.add(
                        NetworkInterfaceInfo(
                            mac=result.mac,
                            ip=result.ip,
                            dns_hostname=result.host_name,
                        )
                    )

        return devices

    @staticmethod
    def map_pets_to_devices(devices: set[NetworkInterfaceInfo],
                            pets: Iterable[PetData]) -> dict[str, NetworkInterfaceInfo]:
        matches: dict[str, NetworkInterfaceInfo] = {}
        for pet in pets:
            field_name = {
                PetData.PrimaryIdentifier.IP: 'ip',
                PetData.PrimaryIdentifier.MAC: 'mac',
                PetData.PrimaryIdentifier.HOST: 'dns_hostname',
            }[PetData.PrimaryIdentifier[pet.identifier_type]]
            matches[pet.name] = NetworkInterfaceInfo(**{field_name: pet.identifier_value})
            for device in devices:
                if getattr(device, field_name) == pet.identifier_value:
                    matches[pet.name] = device
                    break
        return matches
