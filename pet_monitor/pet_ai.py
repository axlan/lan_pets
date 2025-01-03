import logging
import random
from collections import defaultdict
from enum import IntEnum
from typing import Iterable, NamedTuple, Optional

from pet_monitor.common import (DATA_DIR, delete_missing_names,
                                get_db_connection)
from pet_monitor.settings import MoodAlgorithm, PetAISettings, RateLimiter

_logger = logging.getLogger(__name__)


class MoodAttributes(NamedTuple):
    rx_bps: float
    tx_bps: float
    on_line: bool
    availability: float
    history_len_sec: float


class Moods(IntEnum):
    JOLLY = 1
    SASSY = 2
    CALM = 3
    MODEST = 4
    DREAMY = 5
    IMPISH = 6
    SNEAKY = 7
    SHY = 8


class Relationships(IntEnum):
    FRIENDS = 1


# TODO: There's probably a better way to encode the relationship, or enforce uniqueness:
# https://dba.stackexchange.com/questions/261309/best-way-to-model-the-relationship-of-unique-pairs
SCHEMA_SQL = '''\
CREATE TABLE pet_moods (
    row_id INTEGER NOT NULL,
    name VARCHAR(255),                  -- Name of the pet
    mood INT,                  -- Mood of the pet
    UNIQUE (name),                       -- Ensure names unique
    PRIMARY KEY(row_id)
);

CREATE TABLE pet_relationships (
    name1_id INT,                   -- Name that comes first alphabetically
    name2_id INT,                   -- Name that comes last alphabetically
    relationship INT,               -- Relationship between pets
    FOREIGN KEY(name1_id) REFERENCES pet_moods(row_id) ON DELETE CASCADE,
    FOREIGN KEY(name2_id) REFERENCES pet_moods(row_id) ON DELETE CASCADE
);
'''


def _get_mood(stats: MoodAttributes, settings: PetAISettings):
    if settings.mood_algorithm is MoodAlgorithm.RANDOM:
        return random.choice(tuple(m for m in Moods))
    else:
        return Moods.JOLLY


class relationship_iter:
    def __init__(self) -> None:
        self.relationships: set[tuple[str, str, Relationships]] = set()

    def _get_entry(self, name1: str, name2: str):
        value = None
        for info in self.relationships:
            if name1 in info and name2 in info:
                value = info
                break
        return value

    def add(self, name1: str, name2: str, relationship: Relationships):
        self.relationships.add((name1, name2, relationship))

    def remove(self, name1: str, name2: str):
        value = self._get_entry(name1, name2)
        if value is not None:
            self.relationships.remove(value)

    def get_relationships(self, name: str) -> dict[str, Relationships]:
        this_relationship: dict[str, Relationships] = {}
        for info in self.relationships:
            if info[0] == name:
                this_relationship[info[1]] = info[2]
            elif info[1] == name:
                this_relationship[info[0]] = info[2]
        return this_relationship

    def get_relationship(self, name1: str, name2: str) -> Optional[Relationships]:
        value = self._get_entry(name1, name2)
        if value is not None:
            return value[2]
        return None


class PetAi:

    def __init__(self, settings: PetAISettings) -> None:
        self.rate_limiter = RateLimiter(settings.update_period_sec)
        self.settings = settings
        self.conn = get_db_connection(DATA_DIR / 'pet_moods.sqlite3', SCHEMA_SQL)

    def get_moods(self, names: Iterable[str]) -> dict[str, Moods]:
        moods = {n: Moods.JOLLY for n in names}
        cur = self.conn.cursor()
        NAME_STRS = ','.join([f'"{n}"' for n in names])
        QUERY = f"""
            SELECT name, mood
            FROM pet_moods
            WHERE name IN ({NAME_STRS});"""
        cur.execute(QUERY)
        for r in cur.fetchall():
            moods[r[0]] = Moods(r[1])
        return moods

    def get_all_relationships(self) -> set[tuple[str, str, Relationships]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT name1.name, name2.name, relationship
            FROM pet_relationships
            JOIN pet_moods name1
            ON name1.row_id = name1_id
            JOIN pet_moods name2
            ON name2.row_id = name2_id;""")
        return {(r[0], r[1], Relationships(r[2])) for r in cur.fetchall()}

    def get_relationships(self, names: Iterable[str]) -> relationship_iter:
        relationships = relationship_iter()
        NAME_STRS = ','.join([f'"{n}"' for n in names])
        cur = self.conn.cursor()
        cur.execute(
            f"""
            SELECT name1.name, name2.name, relationship
            FROM pet_relationships
            JOIN pet_moods name1
            ON name1.row_id = name1_id
            JOIN pet_moods name2
            ON name2.row_id = name2_id
            WHERE name1.name IN ({NAME_STRS}) OR name2.name IN ({NAME_STRS});""")
        for r in cur.fetchall():
            relationships.add(r[0], r[1], Relationships(r[2]))
        return relationships

    @staticmethod
    def get_ordered_names(name1: str, name2: str) -> tuple[str, str]:
        return (name1, name2) if name1 < name2 else (name2, name1)

    def update(self, pets: dict[str, MoodAttributes]) -> None:
        if not self.rate_limiter.get_ready():
            return

        # Clear deleted pets
        delete_missing_names(self.conn, 'pet_moods', [n for n in pets])

        online_pets = {k for k, p in pets.items() if p.on_line}
        all_relationships = self.get_relationships(online_pets)
        previous_moods = self.get_moods(pets)

        for name, stats in pets.items():
            # TODO: Update moods based on attributes.
            mood = _get_mood(stats, self.settings)
            if mood is not previous_moods[name]:
                _logger.info(f'{name} went from {previous_moods[name].name} to {mood.name}')
            self.conn.execute(
                '''INSERT INTO pet_moods(name,mood) VALUES(?, ?)
                    ON CONFLICT(name) DO UPDATE SET mood=?;''', (name, int(mood), int(mood)))
            self.conn.commit()

            # TODO: Add other relationships
            if stats.on_line:
                pet_relationships = all_relationships.get_relationships(name)
                potentials = {
                    n for n in online_pets if (
                        pet_relationships is None or n not in pet_relationships) and n != name}
                if pet_relationships is not None and len(pet_relationships) > 0:
                    if random.uniform(0, 1) < self.settings.prob_lose_friend:
                        breakup_name = random.choice([n for n in pet_relationships])
                        _logger.info(f'Breaking up {name} and {breakup_name}')
                        all_relationships.remove(name, breakup_name)
                        names = self.get_ordered_names(name, breakup_name)
                        self.conn.execute("""
                                    DELETE FROM pet_relationships
                                    WHERE rowid IN (
                                        SELECT a.rowid FROM pet_relationships a
                                        JOIN pet_moods name1
                                            ON name1.row_id = name1_id
                                        JOIN pet_moods name2
                                            ON name2.row_id = name2_id
                                        WHERE name1.name = ? AND name2.name = ?
                                    );""", names)
                        self.conn.commit()

                if len(potentials) > 0:
                    prob_new_friend = max(
                        self.settings.prob_make_friend -
                        self.settings.prob_make_friend_per_friend_drop,
                        0)
                    if random.uniform(0, 1) < prob_new_friend:
                        friend_name = random.choice([n for n in potentials])
                        _logger.info(f'Friendship between {name} and {friend_name}')
                        names = self.get_ordered_names(name, friend_name)
                        all_relationships.add(names[0], names[1], Relationships.FRIENDS)
                        self.conn.execute("""
                                    INSERT INTO pet_relationships (name1_id, name2_id, relationship)
                                    SELECT name1.row_id, name2.row_id, ?
                                    FROM
                                        (SELECT row_id from pet_moods WHERE name=?) name1,
                                        (SELECT row_id from pet_moods WHERE name=?) name2;""", (int(Relationships.FRIENDS), *names))
                        self.conn.commit()
