

import logging
import time
from enum import Enum, auto
from typing import NamedTuple, Optional

from pet_monitor.common import ClientInfo

_logger = logging.getLogger(__name__)


class PingerSettings(NamedTuple):
    update_period_sec = 10.0


class MoodAlgorithm(Enum):
    RANDOM = auto()
    ACTIVITY1 = auto()


class PetAISettings(NamedTuple):
    update_period_sec = 60.0 * 60.0

    # Mood parameters.
    mood_algorithm = MoodAlgorithm.ACTIVITY1
    history_window_sec = update_period_sec
    uptime_percent_for_available = 50.0
    average_bytes_per_sec_for_loud = 10.0

    # Interaction parameters.
    prob_message_friend = 0.05
    prob_make_friend = 0.2
    prob_make_friend_per_friend_drop = 0.05
    prob_lose_friend = 0.05


class TPLinkSettings(NamedTuple):
    router_ip: str
    username: str
    password: str
    update_period_sec = 60.0 * 10


class NMAPSettings(NamedTuple):
    ip_ranges = '192.168.1.1-255'
    use_sudo = True
    ping_timeout = 1.0
    time_between_scans = 60.0 * 10.0


class Settings(NamedTuple):
    tplink_settings: Optional[TPLinkSettings] = None
    nmap_settings: Optional[NMAPSettings] = NMAPSettings()
    hard_coded_clients: set[ClientInfo] = {
        ClientInfo(
            mac='44-AF-28-12-11-E6',
            ip='192.168.1.88',
            client_name='Zephurus'
        ),
        ClientInfo(
            mac='1A-F3-51-12-36-EB',
            ip='192.168.1.86',
            client_name='Pixel 8'
        ),
    }
    main_loop_sleep_sec = 0.1
    plot_timezone = 'America/Los_Angeles'
    plot_data_window_sec = 60.0 * 60.0 * 24.0 * 7.0
    pinger_settings = PingerSettings()
    pet_ai_settings = PetAISettings()

    def hard_coded_client_info(self) -> dict[str, ClientInfo]:
        return {c.mac: c for c in self.hard_coded_clients}

    def hard_coded_mac_ip_map(self) -> set[tuple[str, str]]:
        return {(c.mac, c.ip) for c in self.hard_coded_clients if c.ip is not None}


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
