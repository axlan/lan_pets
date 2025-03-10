

import logging
import time
from enum import Enum, auto
from typing import NamedTuple, Optional

from pet_monitor.common import NetworkInterfaceInfo

_logger = logging.getLogger(__name__)

# week
MAX_HISTORY_LEN_SEC = 60.0 * 60.0 * 24.0 * 7.0


class PingerSettings(NamedTuple):
    '''
    Settings for periodically sending ICMP ping to each pet.
    '''
    update_period_sec = 60.0
    history_len = MAX_HISTORY_LEN_SEC


class MoodAlgorithm(Enum):
    '''
    Algorithm to use for checking what mood each pet is.
    '''
    # Change at random
    RANDOM = auto()
    # Change based on bandwidth usage and uptime.
    ACTIVITY1 = auto()
    # Change based on bandwidth usage, num services, and uptime.
    ACTIVITY_SERVICES = auto()


class PetAISettings(NamedTuple):
    '''
    Settings for determining pet behavior.
    '''
    # How often should the behavior update algorithms run.
    update_period_sec = 60.0 * 60.0

    # Which mood algorithm to use.
    mood_algorithm = MoodAlgorithm.ACTIVITY_SERVICES
    # How long a window of data should be used for determining moods.
    history_window_sec = update_period_sec
    # Above what uptime percentage is considered "available"
    uptime_percent_for_available = 50.0
    # Above what byte rate is considered high bandwidth.
    average_bytes_per_sec_for_loud = 10.0

    # What is the chance a pet will make a friend each update.
    prob_make_friend = 0.2
    # How does this percentage go down for each existing friend a pet has.
    prob_make_friend_per_friend_drop = 0.05
    # What is the chance a pet will break up with a friend.
    prob_lose_friend = 0.05
    # How much more likely to make friends with compatible moods.
    friend_mood_multiplier = 4.0

    # What is the chance a pet will make a enemy each update.
    prob_make_enemy = 0.2
    # How does this percentage go down for each existing enemy a pet has.
    prob_make_enemy_per_enemy_drop = 0.2
    # What is the chance a pet will break up with an enemy.
    prob_lose_enemy = 0.05


class TPLinkSettings(NamedTuple):
    '''
    Parameters for scraping TPLink router.
    '''
    router_ip: str
    username: str
    password: str
    collect_traffic_data = True
    update_period_sec = 60.0 * 10
    history_len = MAX_HISTORY_LEN_SEC


class NMAPSettings(NamedTuple):
    '''
    Parameters for running NMAP scans.
    '''
    ip_ranges = '192.168.1.1-255'
    use_sudo = False
    nmap_flags = "--open -T4"
    time_between_scans = 60.0 * 10.0


class SNMPSettings(NamedTuple):
    '''
    Parameters for running SNMP queries.
    '''
    router_ip = "192.168.1.1"
    community = 'public'
    time_between_scans = 60.0 * 10.0
    collect_traffic_data = False
    history_len = MAX_HISTORY_LEN_SEC


class MDNSSettings(NamedTuple):
    '''
    Parameters for running mDNS queries.
    '''
    time_between_updates = 60.0 * 10.0


class Settings(NamedTuple):
    # Network discovery sources
    tplink_settings: Optional[TPLinkSettings] = None
    nmap_settings: Optional[NMAPSettings] = NMAPSettings()
    snmp_settings: Optional[SNMPSettings] = SNMPSettings()
    mdns_settings: Optional[MDNSSettings] = MDNSSettings()

    # List of clients to include even if they aren't discovered
    hard_coded_pet_interfaces: dict[str, NetworkInterfaceInfo] = {}

    # How long to sleep between checking services
    main_loop_sleep_sec = 0.1

    # Timezone to use for plots.
    plot_timezone = 'America/Los_Angeles'
    # Time window to draw in plots.
    plot_data_window_sec = MAX_HISTORY_LEN_SEC

    pinger_settings: Optional[PingerSettings] = PingerSettings()
    pet_ai_settings = PetAISettings()


def get_settings() -> Settings:
    '''
    Merge defaults from this file with results lodad from `pet_monitor/secret_settings.py`
    '''
    tplink_settings = None
    try:
        from pet_monitor import secret_settings
        if hasattr(secret_settings, 'tplink_settings'):
            tplink_settings = secret_settings.tplink_settings
        else:
            _logger.debug("No tplink settings to load.")
    except (ModuleNotFoundError, ImportError):
        _logger.warning("No secret settings to load.")

    return Settings(tplink_settings=tplink_settings)


if __name__ == '__main__':
    print(get_settings())
