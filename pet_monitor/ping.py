from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
from typing import Iterable, NamedTuple

from icmplib import ping

from pet_monitor.constants import DATA_DIR
from pet_monitor.settings import PingerSettings, RateLimiter, get_settings


class PingerItem(NamedTuple):
    name: str
    hostname: str


SCHEMA_SQL = '''\
CREATE TABLE ping_names (
    name VARCHAR(255),                  -- Name of the pet
    UNIQUE (name)                       -- Ensure names unique
);

CREATE TABLE ping_results (
    name_id INT,                   -- Index of ping_names table entry
    is_connected BOOLEAN,          -- Did ping succeed
    timestamp INTEGER DEFAULT (strftime('%s', 'now')), -- Unix time of observation
    FOREIGN KEY(name_id) REFERENCES ping_names(rowid)
);

'''


def create_database_from_schema(db_path):
    """Create a new SQLite database from a schema file if it doesn't exist."""
    print(f"Database '{db_path}' does not exist. Creating from schema file...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.executescript(SCHEMA_SQL)
        conn.commit()
        print(f"Database '{db_path}' created successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred while creating the database: {e}")
    finally:
        conn.close()


class Pinger:

    def __init__(self, settings: PingerSettings) -> None:
        self.rate_limiter = RateLimiter(settings.update_period_sec)
        self.db_path = DATA_DIR / 'ping_results.sqlite3'

        if not os.path.exists(self.db_path):
            create_database_from_schema(self.db_path)

    def load_availability(self, names:Iterable[str]) -> dict[str, tuple[bool, float]]:
        availability = {}
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            for name in names:
                cur.execute(
                    """
                    SELECT CAST(SUM(r.is_connected) AS FLOAT) / COUNT(*) * 100 ConnectedPct
                    FROM ping_results r
                    JOIN ping_names n
                    ON r.name_id = n.rowid
                    WHERE n.name=?;""", (name,))
                result = cur.fetchone()
                print(result)
                up_ratio = 0.0 if result[0] is None else result[0]
                cur.execute(
                    """
                    SELECT r.is_connected
                    FROM ping_results r
                    JOIN ping_names n
                    ON r.name_id = n.rowid
                    WHERE n.name=?
                    ORDER BY r.timestamp DESC
                    LIMIT 1;""", (name,))
                result = cur.fetchone()
                is_online = False if result[0] is None else result[0]
                availability[name] = tuple((is_online, up_ratio))

        return availability

    def get_history_len(self, names:Iterable[str]) -> dict[str, int]:
        availability = {}
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            for name in names:
                cur.execute(
                    """
                    SELECT max(r.timestamp) - min(r.timestamp) HistoryAge
                    FROM ping_names n
                    JOIN ping_results r
                    ON r.name_id = n.rowid
                    WHERE n.name=?
                    LIMIT 1;""", (name,))
                result = cur.fetchone()
                availability[name] = 0.0 if result[0] is None else result[0]
        return availability

    @staticmethod
    def _check_host(pet: PingerItem, db_path: Path) -> None:
        is_up = False
        try:
            host = ping(pet.hostname, count=1, timeout=1, privileged=False)
            is_up = host.packets_sent == host.packets_received
        except Exception:
            pass

        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.execute(
                    "SELECT rowid FROM ping_names WHERE name = ?", (pet.name,))
                result = cur.fetchone()
                if result is None:
                    cur = conn.execute(
                        'INSERT INTO ping_names (name) VALUES (?)', (pet.name,))
                    conn.commit()
                    name_id = cur.lastrowid
                else:
                    name_id = result[0]

                conn.execute(
                    'INSERT INTO ping_results (name_id, is_connected) VALUES (?, ?)', (name_id, is_up))
                conn.commit()
        except Exception as e:
            print(f"Error inserting ping result for {pet.name}: {e}")

    def update(self, pets: list[PingerItem]) -> None:
        if not self.rate_limiter.get_ready():
            return

        # Ideally, don't block on this. Leaving the scope waits for all threads to finish.
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(
                self._check_host, pet, self.db_path) for pet in pets]

def main():
    settings = get_settings().pinger_settings
    if settings is None:
        print("Pinger settings not found.")
        return
    pinger = Pinger(settings)

    print(pinger.load_availability(['zephyrus', 'Nest-Hello-5b0c']))
    #print(pinger.get_history_len(['zephyrus', 'Thermo']))


if __name__ == '__main__':
    main()
