
from enum import IntEnum
import json
import logging
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
    JOLLY = 1
    SASSY = 2
    CALM = 3
    MODEST = 4
    DREAMY = 5
    IMPISH = 6
    SNEAKY = 7
    SHY = 8


class Relationship(IntEnum):
    FRIENDS = 1


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
    description_json: str = '{}'

    def get_description(self) -> dict[str, str]:
        return json.loads(self.description_json)
    
    def get_name(self) -> Optional[str]:
        description = self.get_description()
        if 'dhcp_name' in description:
            return description['dhcp_name']
        elif self.dns_hostname:
            return self.dns_hostname
        else:
            return None
        
    def get_description_str(self) -> Optional[str]:
        description = self.get_description()
        return description.get('router_description')

    def replace_description(self, description: dict[str, str]) -> 'NetworkInterfaceInfo':
        return self._replace(description_json=json.dumps(description, sort_keys=True))
    
    def replace_description_field(self, name: str, value: str) -> 'NetworkInterfaceInfo':
        description = self.get_description()
        description[name] = value
        return self._replace(description_json=json.dumps(description, sort_keys=True))

    def get_timestamp_age_str(self, now_interval=0) -> str:
        return get_timestamp_age_str(self.timestamp, now_interval)

    def is_duplicate(self, other: 'NetworkInterfaceInfo') -> bool:
        def _match(a: Optional[str], b: Optional[str]) -> bool:
            return a is not None and a == b
        return _match(self.ip, other.ip) or _match(self.mac, other.mac) or _match(
            self.dns_hostname, other.dns_hostname)

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
                    new_description = json.loads(older_record_dict['description_json'])
                    new_description.update(newer_record.get_description())
                    missing = {'description_json': json.dumps(new_description, sort_keys=True)}
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
            if getattr(device, field_name) == pet.identifier_value:
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
