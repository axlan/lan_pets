
# TODO: Add concept of plugins for gathering different types of data. This can be enabled on a per device basis.
# TODO: For now assume TPLink scraper to get device IP's.

import logging
import os
import time

# Django setup so model modules import without errors.
from django.apps import apps

from lan_pets.settings import INSTALLED_APPS

# Could use:
# from django.conf import settings
# settings.configure(**conf)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lan_pets.settings")
apps.populate(INSTALLED_APPS)
from manage_pets.models import PetData
from pet_monitor.common import (CONSOLE_LOG_FILE, LoggingTimeFilter,
                                get_empty_traffic)
from pet_monitor.pet_ai import MoodAttributes, PetAi
from pet_monitor.ping import Pinger, PingerItem
from pet_monitor.settings import get_settings
from pet_monitor.network_scanner import NetworkScanner

_logger = logging.getLogger('pet_monitor.pet_monitor_service')


def main():
    fh = logging.FileHandler(CONSOLE_LOG_FILE)
    fh.setLevel(logging.INFO)
    fh.addFilter(LoggingTimeFilter())
    fh.setFormatter(logging.Formatter('%(unix_time)s: %(message)s'))

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    logger_group = logging.getLogger('pet_monitor')
    logger_group.addHandler(ch)
    logger_group.addHandler(fh)
    logger_group.setLevel(logging.DEBUG)

    try:
        settings = get_settings()
        scanner = NetworkScanner(settings)
        pinger = Pinger(settings.pinger_settings)
        pet_ai = PetAi(settings.pet_ai_settings)
        monitors = (pinger, pet_ai, scanner)

        while True:
            if not any((m.is_ready() for m in monitors)):
                time.sleep(settings.main_loop_sleep_sec)
                continue

            # Scan network for devices.
            scanner.scan_network()

            # Load data for pets added on web page.
            discovered_devices = scanner.get_discovered_devices()
            mapped_pets = scanner.map_pets_to_devices(discovered_devices, PetData.objects.iterator())

            # Get map pets to router IP's.
            if pinger.rate_limiter.is_ready():
                pinger.update(mapped_pets)

            if pet_ai.rate_limiter.is_ready():
                mood_data = {}
                pet_availability = pinger.load_availability_mean(mapped_pets.keys())
                pet_is_up = pinger.load_current_availability(mapped_pets.keys())
                history_len = pinger.get_history_len(mapped_pets.keys())
                traffic_stats = get_empty_traffic(mapped_pets.keys())
                if scanner.tplink_scraper is not None:
                    mac_addresses = [d.mac for d in mapped_pets.values() if d.mac is not None]
                    traffic = scanner.tplink_scraper.load_mean_bps(mac_addresses)
                    for name, device in mapped_pets.items():
                        if device.mac is not None:
                            traffic_stats[name] = traffic[device.mac]
                else:
                    traffic_stats = get_empty_traffic(mapped_pets.keys())

                for name in mapped_pets.keys():
                    mood_data[name] = MoodAttributes(
                        rx_bps=traffic_stats[name].rx_bytes_bps,
                        tx_bps=traffic_stats[name].tx_bytes_bps,
                        on_line=pet_is_up[name],
                        availability=pet_availability[name],
                        history_len_sec=history_len[name]
                    )

                pet_ai.update(mood_data)
    except KeyboardInterrupt:
        pass
    except Exception:
        _logger.error('Unhandled Exception:', exc_info=True)

    _logger.debug('Monitor shutdown')


if __name__ == '__main__':
    main()
