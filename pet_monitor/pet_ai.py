import logging
import random
from typing import NamedTuple

import numpy as np

from pet_monitor.network_db import DBInterface
from pet_monitor.service_base import ServiceBase
from pet_monitor.common import (Mood, Relationship, get_cutoff_timestamp, ExtraNetworkInfoType)
from pet_monitor.settings import MoodAlgorithm, PetAISettings

_logger = logging.getLogger(__name__)


class MoodAttributes(NamedTuple):
    rx_bps: float
    tx_bps: float
    num_services: int
    on_line: bool
    availability: float


def _get_mood(stats: MoodAttributes, median_attributes: MoodAttributes, settings: PetAISettings) -> Mood:
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
    elif settings.mood_algorithm is MoodAlgorithm.ACTIVITY_SERVICES:
        present = stats.availability > median_attributes.availability
        high_rx = stats.rx_bps > median_attributes.rx_bps
        high_services = stats.num_services > median_attributes.num_services
        return {
            (True, True, True): Mood.JOLLY,
            (True, False, True): Mood.CALM,
            (False, True, True): Mood.SASSY,
            (False, False, True): Mood.MODEST,
            (True, True, False): Mood.DREAMY,
            (True, False, False): Mood.IMPISH,
            (False, True, False): Mood.SNEAKY,
            (False, False, False): Mood.SHY,
        }[(high_services, high_rx, present)]
    else:
        return Mood.JOLLY


def _get_best_friends(mood: Mood) -> set[Mood]:
    return {Mood((int(mood) + i) % len(Mood)) for i in (-1, 0, 1)}


class PetAi(ServiceBase):
    def __init__(self, settings: PetAISettings) -> None:
        super().__init__(settings.update_period_sec)
        self.settings = settings

    def _update(self) -> None:
        with DBInterface() as db_interface:
            cutoff_time = get_cutoff_timestamp(self.settings.history_window_sec)

            pet_info = db_interface.get_pet_info()
            pet_names = [p.name for p in pet_info]
            mapped_pets = db_interface.get_network_info_for_pets(pet_info)
            traffic = db_interface.load_mean_traffic(pet_names, since_timestamp=cutoff_time)
            availability_mean = db_interface.load_availability_mean(pet_names, since_timestamp=cutoff_time)
            extra_info = {}
            num_services = {}
            for name, device in mapped_pets.items():
                extra_info[name] = db_interface.get_extra_network_info(device)
                num_services[name] = 0
                for value in (ExtraNetworkInfoType.MDNS_SERVICES, ExtraNetworkInfoType.NMAP_SERVICES):
                    num_services[name] = max(num_services[name], len(extra_info[name].get(value, '').split(',')))
            current_availability = db_interface.load_current_availability(pet_names)
            pet_attributes = {
                n: MoodAttributes(
                    traffic[n].rx_bytes_bps,
                    traffic[n].tx_bytes_bps,
                    num_services[n],
                    current_availability[n],
                    availability_mean[n],
                )
                for n in pet_names
            }
            media_values = {}
            for key in MoodAttributes._fields:
                media_values[key] = np.median([getattr(a, key) for a in pet_attributes.values()])
            median_pet_attributes = MoodAttributes(**media_values)

            online_pets = [k for k, p in pet_attributes.items() if p.on_line]
            all_relationships = db_interface.get_relationship_map(online_pets)
            previous_moods = {p.name: p.mood for p in pet_info}

            for name, stats in pet_attributes.items():
                # TODO: Update moods based on attributes.
                mood = _get_mood(stats, median_pet_attributes, self.settings)
                if mood is not previous_moods[name]:
                    _logger.info(f'{name} went from {previous_moods[name].name} to {mood.name}')
                db_interface.update_pet_mood(name, mood)

                # TODO: Add other relationships
                if stats.on_line:
                    pet_relationships = all_relationships.get_relationships(name)
                    friends = {n for n, m in pet_relationships.items() if m == Relationship.FRIENDS}
                    enemies = {n for n, m in pet_relationships.items() if m == Relationship.ENEMY}
                    all_potentials = {
                        n for n in online_pets if (
                            pet_relationships is None or n not in pet_relationships) and n != name}
                    potential_best_friends = {n for n in all_potentials if previous_moods[n] in _get_best_friends(mood)}
                    if len(friends) > 0:
                        if random.uniform(0, 1) < self.settings.prob_lose_friend:
                            breakup_name = random.choice([n for n in friends])
                            _logger.info(f'Breaking up {name} and {breakup_name}')
                            all_relationships.remove(name, breakup_name)
                            db_interface.remove_relationship(name, breakup_name)

                    if len(enemies) > 0:
                        if random.uniform(0, 1) < self.settings.prob_lose_enemy:
                            breakup_name = random.choice([n for n in enemies])
                            _logger.info(f'Truce between {name} and {breakup_name}')
                            all_relationships.remove(name, breakup_name)
                            db_interface.remove_relationship(name, breakup_name)

                    if len(all_potentials) > 0:
                        prob_new_friend = max(
                            self.settings.prob_make_friend -
                            self.settings.prob_make_friend_per_friend_drop * len(friends),
                            0)
                        prob_new_best_friend = prob_new_friend * self.settings.friend_mood_multiplier
                        rand_val = random.uniform(0, 1)
                        if rand_val < prob_new_best_friend:
                            potentials = all_potentials if rand_val < prob_new_friend else potential_best_friends
                            if len(potentials) > 0:
                                friend_name = random.choice([n for n in potentials])
                                _logger.info(f'Friendship between {name} and {friend_name}')
                                db_interface.add_relationship(name, friend_name, Relationship.FRIENDS)
                                all_relationships.add(name, friend_name, Relationship.FRIENDS)
                                all_potentials.remove(friend_name)

                        prob_new_enemy = max(
                            self.settings.prob_make_enemy -
                            self.settings.prob_make_enemy_per_enemy_drop * len(enemies),
                            0)
                        rand_val = random.uniform(0, 1)
                        if len(all_potentials) > 0 and rand_val < prob_new_enemy:
                            enemy_name = random.choice([n for n in all_potentials])
                            _logger.info(f'New enmity between {name} and {enemy_name}')
                            db_interface.add_relationship(name, enemy_name, Relationship.ENEMY)
                            all_relationships.add(name, enemy_name, Relationship.ENEMY)
