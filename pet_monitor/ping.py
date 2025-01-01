import io
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, NamedTuple

import pandas as pd
import plotly_express as px
from icmplib import ping

from pet_monitor.common import (DATA_DIR, delete_missing_names,
                                get_db_connection)
from pet_monitor.settings import PingerSettings, RateLimiter, get_settings


class PingerItem(NamedTuple):
    name: str
    hostname: str


SCHEMA_SQL = '''\
CREATE TABLE ping_names (
    row_id INTEGER NOT NULL,
    name VARCHAR(255),                  -- Name of the pet
    UNIQUE (name),                      -- Ensure names unique
    PRIMARY KEY(row_id)
);

CREATE TABLE ping_results (
    name_id INT,                   -- Index of ping_names table entry
    is_connected BOOLEAN,          -- Did ping succeed
    timestamp INTEGER DEFAULT (strftime('%s', 'now')), -- Unix time of observation
    FOREIGN KEY(name_id) REFERENCES ping_names(row_id) ON DELETE CASCADE
);

'''


class Pinger:

    def __init__(self, settings: PingerSettings) -> None:
        self.rate_limiter = RateLimiter(settings.update_period_sec)
        self.conn = get_db_connection(DATA_DIR / 'ping_results.sqlite3', SCHEMA_SQL)

    def load_current_availability(self, names: Iterable[str]) -> dict[str, bool]:
        results = {n: False for n in names}
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT n.name, r.is_connected
            FROM ping_results r
            JOIN ping_names n
            ON r.name_id = n.row_id
            WHERE r.timestamp =(
                SELECT MAX(timestamp)
                FROM ping_results r2
                WHERE r.name_id = r2.name_id
            );""")
        results.update({r[0]: bool(r[1]) for r in cur.fetchall()})
        return results

    def load_availability(self, names: Iterable[str], since_timestamp=0.0) -> pd.DataFrame:
        NAME_STRS = ','.join([f'"{n}"' for n in names])
        QUERY = f"""
            SELECT n.name, r.is_connected, r.timestamp
            FROM ping_results r
            JOIN ping_names n
            ON r.name_id = n.row_id
            WHERE r.timestamp > {since_timestamp} AND n.name IN ({NAME_STRS});"""
        return pd.read_sql(QUERY, self.conn)

    def load_availability_mean(self, names: Iterable[str], since_timestamp=0.0) -> dict[str, float]:
        availability = {n: 0.0 for n in names}
        cur = self.conn.cursor()
        for name in names:
            cur.execute(
                """
                SELECT CAST(SUM(r.is_connected) AS FLOAT) / COUNT(*) * 100 ConnectedPct
                FROM ping_results r
                JOIN ping_names n
                ON r.name_id = n.row_id
                WHERE r.timestamp > ? AND n.name=?;""", (since_timestamp, name))
            result = cur.fetchone()
            if result[0] is not None:
                availability[name] = result[0]

        return availability

    def generate_uptime_plot(self, name: str, since_timestamp=0.0, time_zone='America/Los_Angeles') -> bytes:
        df = self.load_availability([name], since_timestamp)
        df = df[(df['name'] == name)]
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert(time_zone)

        fig = px.line(df, x='timestamp', y="is_connected", line_shape='hv')
        fig.update_traces(mode='lines+markers')
        # fig.write_image('/tmp/pings.png')

        fd = io.BytesIO()
        fig.write_image(fd, format='webp')
        fd.seek(0)
        return fd.read()

    def get_history_len(self, names: Iterable[str]) -> dict[str, int]:
        availability = {}
        cur = self.conn.cursor()
        for name in names:
            cur.execute(
                """
                SELECT max(r.timestamp) - min(r.timestamp) HistoryAge
                FROM ping_names n
                JOIN ping_results r
                ON r.name_id = n.row_id
                WHERE n.name=?
                LIMIT 1;""", (name,))
            result = cur.fetchone()
            availability[name] = 0.0 if result[0] is None else result[0]
        return availability

    @staticmethod
    def _check_host(pet: PingerItem) -> bool:
        try:
            host = ping(pet.hostname, count=1, timeout=1, privileged=False)
            return host.packets_sent == host.packets_received
        except Exception:
            return False

    def update(self, pets: list[PingerItem]) -> None:
        if not self.rate_limiter.get_ready():
            return

        # Clear deleted pets
        delete_missing_names(self.conn, 'ping_names', [p.name for p in pets])

        # Ideally, don't block on this. Leaving the scope waits for all threads to finish.
        with ThreadPoolExecutor() as executor:
            for pet, is_online in zip(pets, executor.map(self._check_host, pets)):
                cur = self.conn.execute(
                    "SELECT row_id FROM ping_names WHERE name = ?", (pet.name,))
                result = cur.fetchone()
                if result is None:
                    cur = self.conn.execute(
                        'INSERT INTO ping_names (name) VALUES (?)', (pet.name,))
                    self.conn.commit()
                    name_id = cur.lastrowid
                else:
                    name_id = result[0]
                self.conn.execute(
                    'INSERT INTO ping_results (name_id, is_connected) VALUES (?, ?)', (name_id, is_online))
                self.conn.commit()


def main():
    settings = get_settings().pinger_settings
    if settings is None:
        print("Pinger settings not found.")
        return
    pinger = Pinger(settings)

    # print(pinger.load_availability(['bee', 'Nest-Hello-5b0c']))
    pinger.generate_uptime_plot('bee')

    # print(pinger.get_history_len(['zephyrus', 'Thermo']))


if __name__ == '__main__':
    main()
