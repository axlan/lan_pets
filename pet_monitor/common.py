
import os
from pathlib import Path
import sqlite3
from typing import Collection, Iterable, NamedTuple, Optional


DATA_DIR = Path(__file__).parents[1].resolve() / 'data'


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


def get_empty_traffic(mac_addresses: Iterable[str]) -> dict[str, TrafficStats]:
    return {m:TrafficStats(0,0,0,0,0) for m in mac_addresses}


def get_db_connection(db_path: Path, sql_schema: str) -> sqlite3.Connection:
    db_needs_init = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = 1")
    if db_needs_init:
        print(f"Database '{db_path}' does not exist. Creating from schema file...")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = 1")
        cursor = conn.cursor()
        cursor.executescript(sql_schema)
        conn.commit()
        print(f"Database '{db_path}' created successfully.")
    return conn


def delete_missing_names(conn: sqlite3.Connection, table: str, names: Collection[str]) -> None:
    cur = conn.cursor()
    place_holders = ', '.join(['?'] * len(names))
    QUERY = f"DELETE FROM {table} WHERE name NOT IN ({place_holders})"
    cur.execute(QUERY, tuple(n for n in names))
    conn.commit()
