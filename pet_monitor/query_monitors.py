from typing import Iterable, Optional

from pet_monitor.common import NetworkInterfaceInfo, TrafficStats
from pet_monitor.settings import Settings
from pet_monitor.tplink_scraper.scraper import TPLinkScraper
from pet_monitor.nmap.nmap_scraper import NMAPScraper
from pet_monitor.ping import Pinger
from manage_pets.models import PetData


class QueryMonitors:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tplink_scraper = None if self.settings.tplink_settings is None else TPLinkScraper(
            self.settings.tplink_settings)
        self.nmap_scraper = None if self.settings.nmap_settings is None else NMAPScraper(self.settings.nmap_settings)
        self.pinger = None if self.settings.pinger_settings is None else Pinger(self.settings.pinger_settings)

    def get_discovered_devices(self) -> set[NetworkInterfaceInfo]:
        devices: set[NetworkInterfaceInfo] = self.settings.hard_coded_interface_info
        if self.tplink_scraper:
            info = self.tplink_scraper.load_info()
            devices = NetworkInterfaceInfo.merge(devices, {
                NetworkInterfaceInfo(
                    # If the address wasn't reserved, assume the device was seen in the last 2 hours.
                    timestamp=client.timestamp if client.is_reserved else client.timestamp - 60 * 60 * 2,
                    mac=client.mac,
                    ip=client.ip,
                    dhcp_name=client.client_name,
                    router_description=client.description
                )
                for client in info.values()
            })

        if self.nmap_scraper:
            results = self.nmap_scraper.get_all_results()
            devices = NetworkInterfaceInfo.merge(devices, {
                NetworkInterfaceInfo(
                    timestamp=result.timestamp,
                    mac=result.mac,
                    ip=result.ip,
                    dns_hostname=result.host_name,
                )
                for result in results
            })

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
            matches[pet.name] = NetworkInterfaceInfo(**{field_name: pet.identifier_value})  # type: ignore
            for device in devices:
                if getattr(device, field_name) == pet.identifier_value:
                    matches[pet.name] = device
                    break
        return matches

    def load_mean_bps(self, devices: set[NetworkInterfaceInfo], since_timestamp: Optional[float] = None) -> dict[NetworkInterfaceInfo, TrafficStats]:
        results = {}
        if self.tplink_scraper is not None:
            mac_devices = set(d for d in devices if d.mac is not None)
            macs: list[str] = [d.mac for d in mac_devices]  # type: ignore
            
            for mac, stats in self.tplink_scraper.load_mean_bps(macs, since_timestamp).items():
                device = next((d for d in mac_devices if d.mac == mac), None)
                if device:
                    results[device] = stats
                
        return results

    def generate_traffic_plot(self, device: NetworkInterfaceInfo, since_timestamp: Optional[float] = None) -> Optional[bytes]:
        if self.tplink_scraper is not None and device.mac is not None:
            return self.tplink_scraper.generate_traffic_plot(device.mac, since_timestamp)

        return None

    def load_availability_mean(self, devices: set[NetworkInterfaceInfo]):
        pass

    def generate_uptime_plot(self, device: NetworkInterfaceInfo) -> Optional[bytes]:
        if self.pinger is not None and device.ip is not None:
            return self.tplink_scraper.generate_traffic_plot(device.mac, since_timestamp)

        return None
