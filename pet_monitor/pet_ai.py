import logging
import random
from typing import NamedTuple

from pet_monitor.network_db import get_db_connection, get_pet_info, load_mean_traffic, load_current_availability, load_availability_mean, get_relationship_map, update_pet_mood, add_relationship, remove_relationship
from pet_monitor.service_base import ServiceBase, Condition
from pet_monitor.common import (Mood, Relationship, get_cutoff_timestamp)
from pet_monitor.settings import MoodAlgorithm, PetAISettings

_logger = logging.getLogger(__name__)


class MoodAttributes(NamedTuple):
    rx_bps: float
    tx_bps: float
    on_line: bool
    availability: float


def _get_mood(stats: MoodAttributes, settings: PetAISettings) -> Mood:
    if settings.mood_algorithm is MoodAlgorithm.RANDOM:
        return random.choice(tuple(m for m in Mood))
    elif settings.mood_algorithm is MoodAlgorithm.ACTIVITY1:
        present = stats.availability > settings.uptime_percent_for_available
        high_rx = stats.rx_bps > settings.average_bytes_per_sec_for_loud
        high_tx = stats.tx_bps > settings.average_bytes_per_sec_for_loud
        return {
            (True, True, True): Mood.JOLLY,
            (True, False, True): Mood.SASSY,
            (False, True, True): Mood.CALM,
            (False, False, True): Mood.MODEST,
            (True, True, False): Mood.DREAMY,
            (True, False, False): Mood.IMPISH,
            (False, True, False): Mood.SNEAKY,
            (False, False, False): Mood.SHY,
        }[(high_tx, high_rx, present)]
    else:
        return Mood.JOLLY


class PetAi(ServiceBase):
    def __init__(self, stop_condition: Condition, settings: PetAISettings) -> None:
        super().__init__(settings.update_period_sec, stop_condition)
        self.settings = settings

    def _update(self) -> None:
        conn = get_db_connection()
        cutoff_time = get_cutoff_timestamp(self.settings.history_window_sec)

        pet_info = get_pet_info(conn)
        pet_names = (p.name for p in pet_info)
        traffic = load_mean_traffic(conn, pet_names, since_timestamp=cutoff_time)
        availability_mean = load_availability_mean(conn, pet_names, since_timestamp=cutoff_time)
        current_availability = load_current_availability(conn, pet_names)
        pet_attributes = {
            n: MoodAttributes(
                traffic[n].rx_bytes_bps,
                traffic[n].tx_bytes_bps,
                current_availability[n],
                availability_mean[n],
            )
            for n in pet_names
        }

        online_pets = (k for k, p in pet_attributes.items() if p.on_line)
        all_relationships = get_relationship_map(conn, online_pets)
        previous_moods = {p.name: p.mood for p in pet_info}

        for name, stats in pet_attributes.items():
            # TODO: Update moods based on attributes.
            mood = _get_mood(stats, self.settings)
            if mood is not previous_moods[name]:
                _logger.info(f'{name} went from {previous_moods[name].name} to {mood.name}')
            update_pet_mood(conn, name, mood)

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
                        remove_relationship(conn, name, breakup_name)

                if len(potentials) > 0:
                    prob_new_friend = max(
                        self.settings.prob_make_friend -
                        self.settings.prob_make_friend_per_friend_drop * len(pet_relationships),
                        0)
                    if random.uniform(0, 1) < prob_new_friend:
                        friend_name = random.choice([n for n in potentials])
                        _logger.info(f'Friendship between {name} and {friend_name}')
                        add_relationship(conn, name, friend_name, Relationship.FRIENDS)
