
# TODO: Add concept of plugins for gathering different types of data. This can be enabled on a per device basis.

import logging

from pet_monitor.common import CONSOLE_LOG_FILE, LoggingTimeFilter
from pet_monitor.mdns_service import MDNSScraper
from pet_monitor.network_db import DBInterface
from pet_monitor.nmap.nmap_scraper import NMAPScraper
from pet_monitor.pet_ai import PetAi
from pet_monitor.ping import Pinger
from pet_monitor.service_base import ServiceBase
from pet_monitor.settings import get_settings
from pet_monitor.snmp.snmp_scraper import SNMPScraper
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

    settings = get_settings()
    DBInterface.set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)

    services: list[ServiceBase] = []
    
    if settings.tplink_settings is not None:
        services.append(TPLinkScraper(settings.tplink_settings))
        
    if settings.nmap_settings is not None:
        services.append(NMAPScraper(settings.nmap_settings))

    if settings.snmp_settings is not None:
        services.append(SNMPScraper(settings.snmp_settings))

    if settings.pinger_settings is not None:
        services.append(Pinger(settings.pinger_settings))

    if settings.mdns_settings is not None:
        services.append(MDNSScraper(settings.mdns_settings))

    if settings.pet_ai_settings is not None:
        services.append(PetAi(settings.pet_ai_settings))

    ServiceBase.run_services(services)

    _logger.debug('Monitor shutdown')


if __name__ == '__main__':
    main()
