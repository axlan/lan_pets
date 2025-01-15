

import logging
import time
from enum import Enum, auto
from typing import NamedTuple, Optional

from pet_monitor.common import NetworkInterfaceInfo

_logger = logging.getLogger(__name__)


class PingerSettings(NamedTuple):
    '''
    Settings for periodically sending ICMP ping to each pet.
    '''
    update_period_sec = 10.0


class MoodAlgorithm(Enum):
    '''
    Algorithm to use for checking what mood each pet is.
    '''
    ## Change at random
    RANDOM = auto()
    ## Change based on bandwidth usage and uptime.
    ACTIVITY1 = auto()


class PetAISettings(NamedTuple):
    '''
    Settings for determining pet behavior.
    '''
    # How often should the behavior update algorithms run.
    update_period_sec = 60.0 * 60.0

    # Which mood algorithm to use.
    mood_algorithm = MoodAlgorithm.ACTIVITY1
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


class TPLinkSettings(NamedTuple):
    '''
    Parameters for scraping TPLink router.
    '''
    router_ip: str
    username: str
    password: str
    update_period_sec = 60.0 * 10


class NMAPSettings(NamedTuple):
    '''
    Parameters for running NMAP scans.
    '''
    ip_ranges = '192.168.1.1-255'
    use_sudo = False
    time_between_scans = 60.0 * 10.0


class Settings(NamedTuple):
    # Network discovery sources
    tplink_settings: Optional[TPLinkSettings] = None
    nmap_settings: Optional[NMAPSettings] = NMAPSettings()

    # List of clients to include even if they aren't discovered
    hard_coded_interface_info: set[NetworkInterfaceInfo] = set()

    # How long to sleep between checking services
    main_loop_sleep_sec = 0.1

    # Timezone to use for plots.
    plot_timezone = 'America/Los_Angeles'
    # Time window to draw in plots.
    plot_data_window_sec = 60.0 * 60.0 * 24.0 * 7.0

    pinger_settings = PingerSettings()
    pet_ai_settings = PetAISettings()


class RateLimiter:
    def __init__(self, update_period_sec) -> None:
        self.update_period_sec = update_period_sec
        self.last_update = float('-inf')

    def get_ready(self) -> bool:
        if not self.is_ready():
            return False
        else:
            self.last_update = time.monotonic()
            return True

    def is_ready(self) -> bool:
        return time.monotonic() - self.last_update > self.update_period_sec


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
    except ModuleNotFoundError:
        _logger.warning("No secret settings to load.")

    return Settings(tplink_settings=tplink_settings)


if __name__ == '__main__':
    print(get_settings())
