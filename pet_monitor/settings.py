

from typing import NamedTuple, Optional


class TPLinkSettings(NamedTuple):
    router_ip: str
    username: str
    password: str
    update_period_sec = 3600


class Settings(NamedTuple):
    tplink_settings: Optional[TPLinkSettings]


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
