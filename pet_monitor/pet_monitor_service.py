
# TODO: Add concept of plugins for gathering different types of data. This can be enabled on a per device basis.
# TODO: For now assume TPLink scraper to get device IP's.


import os

# Django setup so model modules import without errors.
from django.apps import apps
from lan_pets.settings import INSTALLED_APPS
# Could use:
# from django.conf import settings
# settings.configure(**conf)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lan_pets.settings")
apps.populate(INSTALLED_APPS)
from manage_pets.models import PetData

from pet_monitor.pet_ai import MoodAttributes, PetAi
from pet_monitor.settings import get_settings
from pet_monitor.ping import Pinger, PingerItem
from pet_monitor.tplink_scraper.scraper import TPLinkScraper


def main():
    settings = get_settings()
    tplink_scraper = None if settings.tplink_settings is None else TPLinkScraper(settings.tplink_settings)
    if tplink_scraper is None:
        raise NotImplementedError('TPLinkScraper currently required.')
    pinger = Pinger(settings.pinger_settings)
    pet_ai = PetAi(settings.pet_ai_settings)

    try:
        while True:
            # Load data for pets added on web page.
            pet_data = {p.name: p for p in PetData.objects.iterator()}
            macs = [p.mac_address for p in pet_data.values()]

            # Router scraping is used for discovery and device metrics.
            tplink_scraper.update()

            # Get map pets to router IP's.
            mac_ip_map = tplink_scraper.load_ips(macs)
            ip_map:dict[str,str] = {}
            for mac, ip in mac_ip_map:
                for pet in pet_data.values():
                    if pet.mac_address == mac:
                        ip_map[pet.name] = ip

            pinger_items = [PingerItem(name=name, hostname=ip) for name, ip in ip_map.items()]
            pinger.update(pinger_items)

            mood_data = {}
            pet_availability = pinger.load_availability(pet_data.keys())
            histort_len = pinger.get_history_len(pet_data.keys())
            traffic_stats = tplink_scraper.load_mean_bps(macs)
            for pet in pet_data.values():
                mood_data[pet.name] = MoodAttributes(
                    rx_bps=traffic_stats[pet.mac_address].rx_bytes_bps,
                    tx_bps=traffic_stats[pet.mac_address].tx_bytes_bps,
                    availability=pet_availability[pet.name],
                    history_len_sec=histort_len[pet.name]
                )
            
            pet_ai.update(mood_data)


    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
