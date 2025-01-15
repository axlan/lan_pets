
from dataclasses import dataclass, asdict, replace
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Collection, Iterable, NamedTuple, Optional, TypeVar

DATA_DIR = Path(__file__).parents[1].resolve() / 'data'
CONSOLE_LOG_FILE = DATA_DIR / 'monitor_service.txt'
_logger = logging.getLogger(__name__)


class ClientInfo(NamedTuple):
    mac: str
    is_reserved: int = 0
    ip: Optional[str] = None
    client_name: Optional[str] = None
    description: Optional[str] = None


class TrafficStats(NamedTuple):
    rx_bytes: float
    tx_bytes: float
    timestamp: int
    rx_bytes_bps: float
    tx_bytes_bps: float


@dataclass(frozen=True)
class NetworkInterfaceInfo:
    '''
    Information gathered from network.
    '''
    # Unix time of last update.
    timestamp: int = 0
    # MAC address of interface.
    mac: Optional[str] = None
    # IPv4 address of interface.
    ip: Optional[str] = None
    # Device's self asserted name.
    # Can come from DHCP. The DHCP protocol allows a "hostname" field to be
    # added in DHCP requests (for a computer to inform about its name) as well
    # as DHCP acknowledgements (for a DHCP server to assign a different
    # hostname). This is specified in RFC 2132 §3.14 for DHCPv4.
    # Can come from netbios, mdns or other service as well.
    dhcp_name: Optional[str] = None
    # Discovered device description. Can come from router static lease notes.
    router_description: Optional[str] = None
    # mDNS string
    mdns_hostname: Optional[str] = None
    # Normal DNS hostname
    dns_hostname: Optional[str] = None
    # Name over netbios
    netbios_name: Optional[str] = None

    @staticmethod
    def merge(vals1: Iterable['NetworkInterfaceInfo'],
              vals2: Iterable['NetworkInterfaceInfo']) -> set['NetworkInterfaceInfo']:
        results = set()
        potential_matches = set(vals2)
        def _match(a: Optional[str], b: Optional[str]) -> bool:
            return a is not None and a == b

        for v1 in vals1:
            # Check for duplicates.
            is_duplicate = False
            for v2 in potential_matches:
                if _match(v1.ip, v2.ip) or _match(v1.mac, v2.mac) or _match(v1.dns_hostname, v2.dns_hostname):
                    newer_record, older_record_dict = (
                        v1, asdict(v2)) if v1.timestamp > v2.timestamp else (
                        v2, asdict(v1))
                    missing = {}
                    for k, v in asdict(newer_record).items():
                        if v is None:
                            missing[k] = older_record_dict[k]
                    results.add(replace(newer_record, **missing))
                    is_duplicate = True
                    potential_matches.remove(v2)
                    break

            if not is_duplicate:
                results.add(v1)
        return results.union(potential_matches)


def get_empty_traffic(names: Iterable[str]) -> dict[str, TrafficStats]:
    return {n: TrafficStats(0, 0, 0, 0, 0) for n in names}


def get_db_connection(db_path: Path, sql_schema: str) -> sqlite3.Connection:
    db_needs_init = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = 1")
    if db_needs_init:
        _logger.debug(f"Database '{db_path}' does not exist. Creating from schema file...")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = 1")
        cursor = conn.cursor()
        cursor.executescript(sql_schema)
        conn.commit()
        _logger.debug(f"Database '{db_path}' created successfully.")
    return conn


def delete_missing_names(conn: sqlite3.Connection, table: str, names: Collection[str]) -> None:
    cur = conn.cursor()
    place_holders = ', '.join(['?'] * len(names))
    QUERY = f"DELETE FROM {table} WHERE name NOT IN ({place_holders})"
    cur.execute(QUERY, tuple(n for n in names))
    conn.commit()


class LoggingTimeFilter(logging.Filter):
    def filter(self, record):
        record.unix_time = int(time.time())
        return True

T = TypeVar('T')
def filter_set(input: Iterable[T], field: str, values: Iterable[Any]) -> set[T]:
    return {
        i for i in input if getattr(i, field) in values
    }
