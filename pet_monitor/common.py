
from enum import IntEnum
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Optional, TypeVar

DATA_DIR = Path(__file__).parents[1].resolve() / 'data'
CONSOLE_LOG_FILE = DATA_DIR / 'monitor_service.txt'


class LoggingTimeFilter(logging.Filter):
    def filter(self, record):
        record.unix_time = int(time.time())
        return True


T = TypeVar('T')
def filter_set(input: Iterable[T], field: str, values: Iterable[Any]) -> set[T]:
    return {
        i for i in input if getattr(i, field) in values
    }


def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def get_timestamp_age_str(timestamp: int, now_interval = 0) -> str:
    age = int(time.time()) - timestamp
    minute = 60
    hour = minute * 60
    day = hour * 24
    week = day * 7
    month = day * 30
    year = day * 365

    if age < now_interval:
        return "now"
    elif age < minute:
        return f'{int(age)} sec'
    elif age < hour:
        return f'{int(age/minute)} min'
    elif age < day:
        return f'{int(age/hour)} hour'
    elif age < week:
        return f'{int(age/day)} day'
    elif age < month:
        return f'{int(age/week)} week'
    elif age < year:
        return f'{int(age/month)} month'
    elif timestamp != 0:
        return 'year+'
    else:
        return 'never'


class IdentifierType(IntEnum):
    MAC = 1
    HOST = 2
    IP = 3


class DeviceType(IntEnum):
    PC = 1
    LAPTOP = 2
    PHONE = 3
    IOT = 4
    SERVER = 5
    ROUTER = 6
    MEDIA = 7
    GAMES = 8
    OTHER = 9


class Mood(IntEnum):
    JOLLY = 0
    CALM = 1
    SASSY = 2
    MODEST = 3
    DREAMY = 4
    IMPISH = 5
    SNEAKY = 6
    SHY = 7


class ExtraNetworkInfoType(IntEnum):
    DHCP_NAME = 1
    ROUTER_DESCRIPTION = 2
    MDNS_NAME = 3
    MDNS_SERVICES = 4
    NMAP_SERVICES = 5


class Relationship(IntEnum):
    FRIENDS = 1
    ENEMY = 2


class PetInfo(NamedTuple):
    name: str
    identifier_type: IdentifierType
    identifier_value: str
    device_type: DeviceType
    description: str = ''
    mood: Mood = Mood.JOLLY


class NetworkInterfaceInfo(NamedTuple):
    '''
    Information gathered from network.
    '''
    # Unix time of last update.
    timestamp: int = 0
    # MAC address of interface.
    mac: Optional[str] = None
    # IPv4 address of interface.
    ip: Optional[str] = None
    # Normal DNS hostname
    dns_hostname: Optional[str] = None
    mdns_hostname: Optional[str] = None

    def get_host(self) -> Optional[str]:
        if self.ip is not None:
            return self.ip 
        elif self.dns_hostname is not None:
            return self.dns_hostname
        return None

    def get_timestamp_age_str(self, now_interval=0) -> str:
        return get_timestamp_age_str(self.timestamp, now_interval)

    def is_duplicate(self, other: 'NetworkInterfaceInfo') -> bool:
        def _match(a: Optional[str], b: Optional[str]) -> bool:
            return a is not None and a == b
        return _match(self.ip, other.ip) or _match(self.mac, other.mac) or _match(
            self.dns_hostname, other.dns_hostname) or _match(
            self.mdns_hostname, other.mdns_hostname)

    @staticmethod
    def merge(vals1: Iterable['NetworkInterfaceInfo'],
              vals2: Iterable['NetworkInterfaceInfo']) -> set['NetworkInterfaceInfo']:
        results = set()
        potential_matches = set(vals2)
        for v1 in vals1:
            # Check for duplicates.
            is_duplicate = False
            for v2 in potential_matches:
                if v1.is_duplicate(v2):
                    newer_record, older_record_dict = (
                        (v1, v2._asdict()) if v1.timestamp > v2.timestamp else (
                            v2, v1._asdict()))
                    missing = {}
                    for k, v in newer_record._asdict().items():
                        if v is None:
                            missing[k] = older_record_dict[k]

                    results.add(newer_record._replace(**missing))
                    is_duplicate = True
                    potential_matches.remove(v2)
                    break

            if not is_duplicate:
                results.add(v1)
        return results.union(potential_matches)

    @staticmethod
    def filter_duplicates(vals: Iterable['NetworkInterfaceInfo']) -> set['NetworkInterfaceInfo']:
        results = set()
        for v1 in vals:
            # Check for duplicates.
            is_duplicate = False
            for v2 in results:
                if v1.is_duplicate(v2):
                    is_duplicate = True
                    break

            if not is_duplicate:
                results.add(v1)
        return results


def map_pets_to_devices(devices: Iterable[NetworkInterfaceInfo],
                        pets: Iterable[PetInfo]) -> dict[str, NetworkInterfaceInfo]:
    matches: dict[str, NetworkInterfaceInfo] = {}
    for pet in pets:
        field_name = {
            IdentifierType.IP: 'ip',
            IdentifierType.MAC: 'mac',
            IdentifierType.HOST: 'dns_hostname',
        }[pet.identifier_type]
        matches[pet.name] = NetworkInterfaceInfo(**{field_name: pet.identifier_value})  # type: ignore
        for device in devices:
            mdns_match = pet.identifier_type is IdentifierType.HOST and device.mdns_hostname == pet.identifier_value
            if mdns_match or getattr(device, field_name) == pet.identifier_value:
                matches[pet.name] = device
                break
    return matches


def get_cutoff_timestamp(max_age_sec) -> int:
    return int(time.time() - max_age_sec)


class TrafficStats(NamedTuple):
    rx_bytes: float = 0
    tx_bytes: float = 0
    timestamp: int = 0
    rx_bytes_bps: float = 0
    tx_bytes_bps: float = 0


class CPUStats(NamedTuple):
    cpu_used_percent: float = 0
    mem_used_percent: float = 0
    timestamp: int = 0


class RelationshipMap:
    def __init__(self) -> None:
        self.relationships: set[tuple[str, str, Relationship]] = set()

    def _get_entry(self, name1: str, name2: str):
        value = None
        for info in self.relationships:
            if name1 in info and name2 in info:
                value = info
                break
        return value

    def add(self, name1: str, name2: str, relationship: Relationship):
        self.relationships.add((name1, name2, relationship))

    def remove(self, name1: str, name2: str):
        value = self._get_entry(name1, name2)
        if value is not None:
            self.relationships.remove(value)

    def get_relationships(self, name: str) -> dict[str, Relationship]:
        this_relationship: dict[str, Relationship] = {}
        for info in self.relationships:
            if info[0] == name:
                this_relationship[info[1]] = info[2]
            elif info[1] == name:
                this_relationship[info[0]] = info[2]
        return this_relationship

    def get_relationship(self, name1: str, name2: str) -> Optional[Relationship]:
        value = self._get_entry(name1, name2)
        if value is not None:
            return value[2]
        return None


def standardize_mac_address(mac: str) -> str:
    # Remove any existing separators
    mac = mac.replace(":", "").replace("-", "").upper()
    # Insert dashes every two characters
    standardized_mac = '-'.join(mac[i:i+2] for i in range(0, len(mac), 2))
    return standardized_mac


def get_mac_for_ip_address(ip_address)->Optional[str]:
    try:
        arp_result = subprocess.check_output(["arp", "-a", str(ip_address)])
        mac_address_search = re.search(r"([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})", arp_result.decode())
        if mac_address_search:
            return standardize_mac_address(mac_address_search.group(0))
    except Exception:
         pass
    return None


def get_device_name(device: NetworkInterfaceInfo, extra_info:dict[ExtraNetworkInfoType, str]) -> Optional[str]:
    if ExtraNetworkInfoType.DHCP_NAME in extra_info:
        return extra_info[ExtraNetworkInfoType.DHCP_NAME]
    elif ExtraNetworkInfoType.MDNS_NAME in extra_info:
        return extra_info[ExtraNetworkInfoType.MDNS_NAME]
    elif device.dns_hostname is not None:
        return device.dns_hostname
    elif device.mdns_hostname is not None:
        return device.mdns_hostname

    return None


def get_device_summary(extra_info:dict[ExtraNetworkInfoType, str]) -> Optional[str]:
    if ExtraNetworkInfoType.ROUTER_DESCRIPTION in extra_info:
        return extra_info[ExtraNetworkInfoType.ROUTER_DESCRIPTION]
    elif ExtraNetworkInfoType.MDNS_SERVICES in extra_info:
        return 'Supports: ' + extra_info[ExtraNetworkInfoType.MDNS_SERVICES]
    elif ExtraNetworkInfoType.NMAP_SERVICES in extra_info:
        return 'Supports: ' + extra_info[ExtraNetworkInfoType.NMAP_SERVICES]

    return None

TRACE = logging.DEBUG - 1
