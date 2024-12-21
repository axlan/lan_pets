

import time
from typing import NamedTuple, Optional


class PingerSettings(NamedTuple):
    update_period_sec = 10.0


class TPLinkSettings(NamedTuple):
    router_ip: str
    username: str
    password: str
    update_period_sec = 3600.0


class Settings(NamedTuple):
    tplink_settings: Optional[TPLinkSettings]
    main_loop_update_period_sec = 1.0
    pinger_settings = PingerSettings()


class RateLimiter:
    def __init__(self, update_period_sec) -> None:
        self.update_period_sec = update_period_sec
        self.last_update = 0.0

    def get_ready(self) -> bool:
        now = time.monotonic()
        if time.monotonic() - self.last_update < self.update_period_sec:
            return False
        self.last_update = now
        return True


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
