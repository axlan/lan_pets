from concurrent.futures import ThreadPoolExecutor
from enum import IntEnum
import os
from pathlib import Path
import sqlite3
from typing import NamedTuple

from pet_monitor.constants import DATA_DIR
from pet_monitor.settings import PetAISettings, RateLimiter


class MoodAttributes(NamedTuple):
    rx_bps: float
    tx_bps: float
    availability: float
    history_len_sec: float


class Moods(IntEnum):
    HAPPY = 1
    SAD = 2
    ANGRY = 3
    SLEEPY = 4
    HUNGRY = 5
    THIRSTY = 6
    PLAYFUL = 7
    SICK = 8
    DEAD = 9

class Relationships(IntEnum):
    FRIENDS = 1


SCHEMA_SQL = '''\
CREATE TABLE pet_moods (
    name VARCHAR(255),                  -- Name of the pet
    mood INT,                  -- Mood of the pet
    UNIQUE (name)                       -- Ensure names unique
);

CREATE TABLE pet_relationships (
    name1_id INT,                   -- Index of ping_names table entry
    name2_id INT,                   -- Index of ping_names table entry
    relationship INT,               -- Relationship between pets
    FOREIGN KEY(name1_id) REFERENCES pet_moods(rowid),
    FOREIGN KEY(name2_id) REFERENCES pet_moods(rowid)
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

def _get_mood(stats: MoodAttributes):
    return Moods.HAPPY

class PetAi:

    def __init__(self, settings: PetAISettings) -> None:
        self.rate_limiter = RateLimiter(settings.update_period_sec)
        self.settings = settings
        self.db_path = DATA_DIR / 'pet_moods.sqlite3'

        if not os.path.exists(self.db_path):
            create_database_from_schema(self.db_path)

    def update(self, pets: dict[str, MoodAttributes]) -> None:
        if not self.rate_limiter.get_ready():
            return

        for name, stats in pets.items():
             mood = _get_mood(stats)
             with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO pet_moods (name, mood) VALUES (?, ?)', (name, int(mood)))
                conn.commit()
