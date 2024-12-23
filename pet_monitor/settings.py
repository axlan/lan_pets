

import time
from typing import NamedTuple, Optional


class PingerSettings(NamedTuple):
    update_period_sec = 10.0


class PetAISettings(NamedTuple):
    update_period_sec = 60.0

    # Mood parameters.
    history_window_sec = 60.0*60.0*24.0*7.0
    uptime_ratio_for_available = 0.5
    average_bytes_per_sec_for_loud = 500

    # Interaction parameters.
    prob_message = 0.5
    prob_message_friend = 0.75
    prob_make_friend = 0.1
    prob_make_friend_per_friend_drop = 0.01
    prob_lose_friend = 0.02


class TPLinkSettings(NamedTuple):
    router_ip: str
    username: str
    password: str
    update_period_sec = 3600.0


class Settings(NamedTuple):
    tplink_settings: Optional[TPLinkSettings] = None
    main_loop_sleep_sec = 0.1
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
    tplink_settings = None
    try:
        from pet_monitor import secret_settings
        if hasattr(secret_settings, 'tplink_settings'):
            tplink_settings = secret_settings.tplink_settings
        else:
            print("No tplink settings to load.")
    except ModuleNotFoundError:
        print("No secret settings to load.")

    return Settings(tplink_settings=tplink_settings)


if __name__ == '__main__':
    print(get_settings())
