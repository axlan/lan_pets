
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
from pet_monitor.tplink_scraper.scraper import TPLinkScraper

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
        tplink_scraper = None if settings.tplink_settings is None else TPLinkScraper(settings.tplink_settings)
        pinger = Pinger(settings.pinger_settings)
        pet_ai = PetAi(settings.pet_ai_settings)
        monitors = {pinger, pet_ai}
        if tplink_scraper is not None:
            monitors.add(tplink_scraper)

        while True:
            if not any((m.rate_limiter.is_ready() for m in monitors)):
                time.sleep(settings.main_loop_sleep_sec)
                continue

            # Load data for pets added on web page.
            pet_data = {p.name: p for p in PetData.objects.iterator()}
            macs = [p.mac_address for p in pet_data.values()]

            # Router scraping is used for discovery and device metrics.
            if tplink_scraper is not None:
                tplink_scraper.update()

            # Get map pets to router IP's.
            if pinger.rate_limiter.is_ready():
                mac_ip_map = settings.hard_coded_mac_ip_map()
                if tplink_scraper is not None:
                    mac_ip_map.update(tplink_scraper.load_ips(macs))
                ip_map: dict[str, str] = {}
                for mac, ip in mac_ip_map:
                    for pet in pet_data.values():
                        if pet.mac_address == mac:
                            ip_map[pet.name] = ip

                pinger_items = [PingerItem(name=name, hostname=ip) for name, ip in ip_map.items()]
                pinger.update(pinger_items)

            if pet_ai.rate_limiter.is_ready():
                mood_data = {}
                pet_availability = pinger.load_availability_mean(pet_data.keys())
                pet_is_up = pinger.load_current_availability(pet_data.keys())
                history_len = pinger.get_history_len(pet_data.keys())
                if tplink_scraper is not None:
                    traffic_stats = tplink_scraper.load_mean_bps(macs)
                else:
                    traffic_stats = get_empty_traffic(macs)

                for pet in pet_data.values():
                    mood_data[pet.name] = MoodAttributes(
                        rx_bps=traffic_stats[pet.mac_address].rx_bytes_bps,
                        tx_bps=traffic_stats[pet.mac_address].tx_bytes_bps,
                        on_line=pet_is_up[pet.name],
                        availability=pet_availability[pet.name],
                        history_len_sec=history_len[pet.name]
                    )

                pet_ai.update(mood_data)
    except KeyboardInterrupt:
        pass
    except Exception:
        _logger.error('Unhandled Exception:', exc_info=True)

    _logger.debug('Monitor shutdown')

if __name__ == '__main__':
    main()
