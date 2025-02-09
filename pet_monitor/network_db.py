
import io
import os
import sqlite3
import time
from collections import defaultdict
from typing import Iterable, Optional, TypeAlias

import pandas as pd
import plotly.graph_objects as go
import plotly_express as px
from plotly.subplots import make_subplots

from pet_monitor.common import (
    DATA_DIR,
    Mood,
    NetworkInterfaceInfo,
    PetInfo,
    Relationship,
    RelationshipMap,
    TrafficStats,
    get_cutoff_time,
    map_pets_to_devices,
)

_DB_PATH = DATA_DIR / 'lan_pets_db.sqlite3'

StrOrBytesPath: TypeAlias = str | bytes | os.PathLike[str] | os.PathLike[bytes]  # stable

NETWORK_INFO_SCHEMA_SQL = '''\
CREATE TABLE IF NOT EXISTS network_info (
    row_id INTEGER NOT NULL,
    mac VARCHAR(17),               -- MAC address (format: XX-XX-XX-XX-XX-XX)
    ip VARCHAR(15),                         -- IP address (format: IPv4). NULL if not available.
    dns_hostname VARCHAR(255),              -- DNS hostname
    mdns_hostname VARCHAR(255),             -- mDNS hostname
    description_json TEXT,                  -- JSON string with additional information about the client
    timestamp INTEGER DEFAULT (strftime('%s', 'now')), -- Unix time last updated
    UNIQUE (mac),                            -- Ensure MAC addresses are unique
    UNIQUE (ip),
    UNIQUE (dns_hostname),
    PRIMARY KEY(row_id)
);
'''

PET_INFO_SCHEMA_SQL = '''\
CREATE TABLE IF NOT EXISTS pet_info (
    row_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    identifier_type INTEGER,
    identifier_value VARCHAR(255),
    device_type INTEGER,
    description TEXT,
    mood INT,                  -- Mood of the pet
    is_deleted BOOL DEFAULT 0,
    UNIQUE (name),
    PRIMARY KEY(row_id)
);
'''

TRAFFIC_STATS_SCHEMA_SQL = '''\
CREATE TABLE IF NOT EXISTS traffic_stats (
    name_id VARCHAR(255) NOT NULL,          -- Name of the device
    rx_bytes INTEGER NOT NULL,              -- Total bytes received
    tx_bytes INTEGER NOT NULL,              -- Total bytes transmitted
    timestamp INTEGER DEFAULT (strftime('%s', 'now')), -- Unix time last updated
    FOREIGN KEY(name_id) REFERENCES pet_info(row_id) ON DELETE CASCADE
);
'''

AVAILABILITY_SCHEMA_SQL = '''\
CREATE TABLE IF NOT EXISTS device_availability (
    name_id INT,                   -- Name of the device
    is_availabile BOOLEAN,         -- Was available
    timestamp INTEGER DEFAULT (strftime('%s', 'now')), -- Unix time of observation
    FOREIGN KEY(name_id) REFERENCES pet_info(row_id) ON DELETE CASCADE
);'''

PET_RELATIONSHIPS_SCHEMA_SQL = '''\
CREATE TABLE IF NOT EXISTS pet_relationships (
    name1_id INT,                   -- Name that comes first alphabetically
    name2_id INT,                   -- Name that comes last alphabetically
    relationship INT,               -- Relationship between pets
    FOREIGN KEY(name1_id) REFERENCES pet_info(row_id) ON DELETE CASCADE,
    FOREIGN KEY(name2_id) REFERENCES pet_info(row_id) ON DELETE CASCADE
);'''


_hard_coded_pet_interfaces = {}


def set_hard_coded_pet_interfaces(info: dict[str, NetworkInterfaceInfo]):
    _hard_coded_pet_interfaces.update(info)


def get_db_connection(db_path: StrOrBytesPath = _DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, autocommit=False)
    conn.execute("PRAGMA foreign_keys = 1")
    conn.execute(NETWORK_INFO_SCHEMA_SQL)
    conn.execute(PET_INFO_SCHEMA_SQL)
    conn.execute(TRAFFIC_STATS_SCHEMA_SQL)
    conn.execute(AVAILABILITY_SCHEMA_SQL)
    conn.execute(PET_RELATIONSHIPS_SCHEMA_SQL)
    return conn


def add_pet_info(conn: sqlite3.Connection, pet: PetInfo):
    field_str = ','.join(PetInfo._fields)
    place_holder_str = ','.join(['?'] * len(PetInfo._fields))
    update_place_holder_str = ','.join(f'{f}=?' for f in PetInfo._fields)
    QUERY = f"""
        INSERT INTO pet_info({field_str}) VALUES ({place_holder_str})
            ON CONFLICT(name) DO UPDATE
            SET {update_place_holder_str}, is_deleted=0;
        """
    conn.execute(QUERY, pet + pet)
    conn.commit()


def update_pet_mood(conn: sqlite3.Connection, name: str, mood: Mood):
    QUERY = """
        UPDATE pet_info
        SET mood=?
        WHERE name=?;
        """
    conn.execute(QUERY, (mood, name))
    conn.commit()


def delete_pet_info(conn: sqlite3.Connection, name: str):
    conn.execute('UPDATE pet_info SET is_deleted=1 WHERE name=?', (name,))
    conn.commit()


def get_pet_info(conn: sqlite3.Connection) -> set[PetInfo]:
    cur = conn.cursor()
    field_str = ','.join(PetInfo._fields)
    QUERY = f"""
        SELECT {field_str}
        FROM pet_info
        WHERE NOT is_deleted;"""
    cur.execute(QUERY)
    return set(PetInfo(*r) for r in cur.fetchall())


def add_network_info(conn: sqlite3.Connection, new_interface: NetworkInterfaceInfo):
    cur = conn.cursor()
    field_str = ','.join(NetworkInterfaceInfo._fields)
    QUERY = f"""
        SELECT row_id, {field_str}
        FROM network_info;"""
    cur.execute(QUERY)
    UNIQUE_PARAMS = {p: i for i, p in enumerate(('ip', 'mac', 'dns_hostname'))}
    current_interfaces = {r[0]: NetworkInterfaceInfo(*r[1:]) for r in cur.fetchall()}
    duplicates: dict[int, list[str]] = defaultdict(list)
    best_duplicate: Optional[tuple[int, int]] = None
    for row_id, interface in current_interfaces.items():
        for param, priority in UNIQUE_PARAMS.items():
            if interface._asdict()[param] and interface._asdict()[param] == new_interface._asdict()[param]:
                duplicates[row_id].append(param)
                if best_duplicate is None or priority > best_duplicate[1]:
                    best_duplicate = (row_id, priority)
    if best_duplicate is None:
        place_holder_str = ','.join(['?'] * len(NetworkInterfaceInfo._fields))
        QUERY = f"INSERT INTO network_info({field_str}) VALUES ({place_holder_str})"
        cur.execute(QUERY, new_interface)
    else:
        for row_id, duplicate_params in duplicates.items():
            if row_id is best_duplicate[0]:
                continue
            else:
                has_valid_fields = any(current_interfaces[row_id]._asdict()[p]
                                       and p not in duplicate_params for p in UNIQUE_PARAMS)
                if has_valid_fields:
                    updates = ','.join(f'{k}=NULL' for k in duplicate_params)
                    QUERY = f"""
                    UPDATE network_info
                    SET {updates}
                    WHERE row_id=?;"""
                    cur.execute(QUERY, (row_id,))
                else:
                    cur.execute('DELETE FROM network_info WHERE row_id=?', (row_id,))
        row_id = best_duplicate[0]
        update_place_holder_str = ','.join(f'{f}=?' for f in NetworkInterfaceInfo._fields)
        new_val = next(iter(NetworkInterfaceInfo.merge([current_interfaces[row_id]], [new_interface])))
        QUERY = f"""
        UPDATE network_info
        SET {update_place_holder_str}
        WHERE row_id=?;"""
        cur.execute(QUERY, new_val + (row_id,))
    conn.commit()


def get_network_info(conn: sqlite3.Connection) -> set[NetworkInterfaceInfo]:
    cur = conn.cursor()
    field_str = ','.join(NetworkInterfaceInfo._fields)
    QUERY = f"""
        SELECT {field_str}
        FROM network_info;"""
    cur.execute(QUERY)
    return set(NetworkInterfaceInfo(*r) for r in cur.fetchall())


def get_network_info_for_pets(conn: sqlite3.Connection, pets: Iterable[PetInfo]) -> dict[str, NetworkInterfaceInfo]:
    return {**_hard_coded_pet_interfaces, **map_pets_to_devices(get_network_info(conn), pets)}


def add_pet_availability(conn: sqlite3.Connection, pet_name: str, is_available: bool, timestamp=int(time.time())):
    QUERY = """
            INSERT INTO device_availability (name_id, is_availabile, timestamp)
            SELECT pet.row_id, ?, ?
            FROM
                (SELECT row_id from pet_info WHERE name=?) pet;"""
    conn.execute(QUERY, (is_available, timestamp, pet_name))
    conn.commit()


def load_last_seen(conn: sqlite3.Connection, names: Iterable[str]) -> dict[str, int]:
    results = {n: 0 for n in names}
    cur = conn.cursor()
    cur.execute("""
        SELECT
            pet_info.name,
            MAX(device_availability.timestamp)
        FROM
            device_availability
        INNER JOIN pet_info ON pet_info.row_id = device_availability.name_id
        WHERE device_availability.is_availabile
        GROUP BY
            device_availability.name_id;""")
    results.update({r[0]: r[1] for r in cur.fetchall() if r[0] in names})
    return results


def load_current_availability(conn: sqlite3.Connection, names: Iterable[str]) -> dict[str, bool]:
    cur = conn.cursor()
    results = {n: False for n in names}
    for name in names:
        cur.execute("""
            SELECT is_availabile
            FROM device_availability
            INNER JOIN pet_info ON pet_info.row_id = device_availability.name_id
            WHERE pet_info.name == ?
            ORDER BY device_availability.rowid DESC
            LIMIT 1;""", (name,))
        cols = cur.fetchone()
        if cols is not None:
            results[name] = bool(cols[0])
    return results


def load_availability(conn: sqlite3.Connection, names: Iterable[str], since_timestamp=0.0) -> pd.DataFrame:
    NAME_STRS = ','.join([f'"{n}"' for n in names])
    QUERY = f"""
        SELECT n.name, r.is_availabile, r.timestamp
        FROM device_availability r
        JOIN pet_info n
        ON r.name_id = n.row_id
        WHERE r.timestamp > {since_timestamp} AND n.name IN ({NAME_STRS});"""
    return pd.read_sql(QUERY, conn)


def load_availability_mean(conn: sqlite3.Connection, names: Iterable[str], since_timestamp=0.0) -> dict[str, float]:
    availability = {n: 0.0 for n in names}
    cur = conn.cursor()
    for name in names:
        cur.execute(
            """
            SELECT CAST(SUM(r.is_availabile) AS FLOAT) / COUNT(*) * 100 ConnectedPct
            FROM device_availability r
            JOIN pet_info n
            ON r.name_id = n.row_id
            WHERE r.timestamp > ? AND n.name=?;""", (since_timestamp, name))
        result = cur.fetchone()
        if result[0] is not None:
            availability[name] = result[0]

    return availability


def generate_uptime_plot(conn: sqlite3.Connection, name: str, since_timestamp=0.0,
                         time_zone='America/Los_Angeles') -> bytes:
    df = load_availability(conn, [name], since_timestamp)
    df = df[(df['name'] == name)]
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert(time_zone)

    fig = px.line(df, x='timestamp', y="is_availabile", line_shape='hv')
    fig.update_traces(mode='lines+markers')
    # fig.write_image('/tmp/pings.png')

    fd = io.BytesIO()
    fig.write_image(fd, format='webp')
    fd.seek(0)
    return fd.read()


def get_history_len(conn: sqlite3.Connection, names: Iterable[str]) -> dict[str, int]:
    availability = {}
    cur = conn.cursor()
    for name in names:
        cur.execute(
            """
            SELECT max(r.timestamp) - min(r.timestamp) HistoryAge
            FROM pet_info n
            JOIN device_availability r
            ON r.name_id = n.row_id
            WHERE n.name=?
            LIMIT 1;""", (name,))
        result = cur.fetchone()
        availability[name] = 0.0 if result[0] is None else result[0]
    return availability


def add_traffic_for_pet(conn: sqlite3.Connection, pet_name: str, rx_bytes: int,
                        tx_bytes: int, timestamp=int(time.time())):
    QUERY = """
            INSERT INTO traffic_stats (name_id, rx_bytes, tx_bytes, timestamp)
            SELECT pet.row_id, ?, ?, ?
            FROM
                (SELECT row_id from pet_info WHERE name=?) pet;"""
    conn.execute(QUERY, (rx_bytes, tx_bytes, timestamp, pet_name))
    conn.commit()


def _load_traffic_df(conn: sqlite3.Connection, names: Iterable[str], since_timestamp: float) -> pd.DataFrame:
    name_strs = ','.join(f'"{n}"' for n in names)
    QUERY = f"""
        SELECT p.name, t.rx_bytes, t.tx_bytes, t.timestamp
        FROM traffic_stats t
        JOIN pet_info p
        ON t.name_id = p.row_id
        WHERE p.name in ({name_strs}) AND t.timestamp >= {since_timestamp}"""
    return pd.read_sql(QUERY, conn)


def load_bps(conn: sqlite3.Connection, names: Iterable[str], since_timestamp: float) -> dict[str, pd.DataFrame]:
    results = {}
    df = _load_traffic_df(conn, names, since_timestamp)
    for name in names:
        pet_df = df[df['name'] == name].dropna().copy()
        pet_df.drop(columns=['name'], inplace=True)
        durations = pet_df['timestamp'].diff()
        for col in ['rx_bytes', 'tx_bytes']:
            bps_col = f'{col}_bps'
            pet_df.loc[:, bps_col] = pet_df[col].diff()
            pet_df.loc[:, bps_col] /= durations
            if len(pet_df) > 0:
                pet_df.loc[pet_df.index[0], bps_col] = 0
            pet_df.loc[pet_df[bps_col] < 0, bps_col] = 0
        results[name] = pet_df
    return results


def get_mean_traffic(pet_bps_set: dict[str, pd.DataFrame], ignore_zero=True) -> dict[str, TrafficStats]:
    results = {}
    for name, pet_df in pet_bps_set.items():
        if len(pet_df) < 2:
            results[name] = TrafficStats()
            continue

        metrics = {}
        metrics['timestamp'] = pet_df['timestamp'].iloc[-1]
        durations = pet_df['timestamp'].diff()
        for col in ['rx_bytes', 'tx_bytes']:
            bps_col = f'{col}_bps'
            diffs = pet_df[bps_col]
            valid_diffs = diffs > 0 if ignore_zero else True
            metrics[bps_col] = (diffs[valid_diffs] / durations[valid_diffs]).mean()  # type: ignore
            metrics[col] = diffs[valid_diffs].sum()
        results[name] = TrafficStats(**metrics)
    return results


def load_mean_traffic(conn: sqlite3.Connection,
                      names: Iterable[str], since_timestamp: float, ignore_zero=True) -> dict[str, TrafficStats]:
    pet_bps_set = load_bps(conn, names, since_timestamp)
    return get_mean_traffic(pet_bps_set, ignore_zero)


def generate_traffic_plot(df: pd.DataFrame, sample_rate='1h', time_zone='America/Los_Angeles') -> bytes:
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert(time_zone)
    df.set_index('timestamp', inplace=True)
    df = df.resample(sample_rate).mean()
    x = df.index
    y1 = df['rx_bytes_bps']
    y2 = df['tx_bytes_bps']

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add traces
    fig.add_trace(go.Scatter(x=x, y=y1, name="Recieved", mode='markers'), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=y2, name="Transmitted", mode='markers'), secondary_y=True)

    # Set y-axes titles
    fig.update_yaxes(title_text="<b>Recieved Bytes/Second</b>", type="log", secondary_y=False)
    fig.update_yaxes(title_text="<b>Transmitted Bytes/Second</b>", type="log", secondary_y=True)
    # fig.write_image('/tmp/scraper.png')

    fd = io.BytesIO()
    fig.write_image(fd, format='webp')
    fd.seek(0)
    return fd.read()


def get_ordered_names(name1: str, name2: str) -> tuple[str, str]:
    return (name1, name2) if name1 < name2 else (name2, name1)


def get_all_relationships(conn: sqlite3.Connection) -> set[tuple[str, str, Relationship]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name1.name, name2.name, relationship
        FROM pet_relationships
        JOIN pet_info name1
        ON name1.row_id = name1_id
        JOIN pet_info name2
        ON name2.row_id = name2_id;""")
    return {(r[0], r[1], Relationship(r[2])) for r in cur.fetchall()}


def get_relationship_map(conn: sqlite3.Connection, names: Iterable[str]) -> RelationshipMap:
    relationships = RelationshipMap()
    NAME_STRS = ','.join([f'"{n}"' for n in names])
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT name1.name, name2.name, relationship
        FROM pet_relationships
        JOIN pet_info name1
        ON name1.row_id = name1_id
        JOIN pet_info name2
        ON name2.row_id = name2_id
        WHERE name1.name IN ({NAME_STRS}) OR name2.name IN ({NAME_STRS});""")
    for r in cur.fetchall():
        relationships.add(r[0], r[1], Relationship(r[2]))
    return relationships


def add_relationship(conn: sqlite3.Connection, name1: str, name2: str, relationship: Relationship):
    names = get_ordered_names(name1, name2)
    conn.execute("""
        INSERT INTO pet_relationships (name1_id, name2_id, relationship)
        SELECT name1.row_id, name2.row_id, ?
        FROM
            (SELECT row_id from pet_info WHERE name=?) name1,
            (SELECT row_id from pet_info WHERE name=?) name2;""", (relationship, *names))
    conn.commit()


def remove_relationship(conn: sqlite3.Connection, name1: str, name2: str):
    names = get_ordered_names(name1, name2)
    conn.execute("""
        DELETE FROM pet_relationships
        WHERE rowid IN (
            SELECT a.rowid FROM pet_relationships a
            JOIN pet_info name1
                ON name1.row_id = name1_id
            JOIN pet_info name2
                ON name2.row_id = name2_id
            WHERE name1.name = ? AND name2.name = ?
        );""", names)
    conn.commit()


def _delete_entries_before(conn: sqlite3.Connection, table: str, cutoff_time: int) -> None:
    conn.execute(f"DELETE FROM {table} WHERE timestamp < ?;", (cutoff_time,))
    conn.commit()


def _delete_old_entries(conn: sqlite3.Connection, table: str, max_age_sec: int) -> None:
    _delete_entries_before(conn, table, get_cutoff_time(max_age_sec))


def delete_old_traffic_stats(conn: sqlite3.Connection, max_age_sec: int) -> None:
    _delete_old_entries(conn, 'traffic_stats', max_age_sec)


def delete_old_availablity(conn: sqlite3.Connection, max_age_sec: int) -> None:
    _delete_old_entries(conn, 'device_availability', max_age_sec)
