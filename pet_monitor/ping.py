import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Generator, Iterable

from icmplib import ping

from pet_monitor.network_db import DBInterface
from pet_monitor.service_base import Condition, ServiceBase, run_services
from pet_monitor.settings import PingerSettings, get_settings

_logger = logging.getLogger(__name__)


def _check_host(address: str) -> bool:
    try:
        host = ping(address, count=1, timeout=1, privileged=False)
        is_online = host.packets_sent == host.packets_received
        _logger.debug(f'ping {address} {is_online}')
        return is_online
    except Exception as e:
        _logger.debug(f'ping {address} {e}')
        return False


def _ping_in_parallel(hosts: Iterable[tuple[str, str]]) -> Generator[tuple[str, bool], None, None]:
    with ThreadPoolExecutor() as executor:
        try:
            names, addresses = zip(*hosts)
        # No entries
        except ValueError:
            return

        for name, is_online in zip(names, executor.map(_check_host, addresses)):
            yield name, is_online


class Pinger(ServiceBase):
    def __init__(self, stop_condition: Condition, settings: PingerSettings) -> None:
        super().__init__(settings.update_period_sec, stop_condition)
        self.settings = settings

    def _update(self) -> None:
        with DBInterface() as db_interface:
            # Clear old data.
            db_interface.delete_old_availablity(int(self.settings.history_len))

            pet_info = db_interface.get_pet_info()
            pet_device_map = db_interface.get_network_info_for_pets(pet_info)

            hosts = set()
            for name, device in pet_device_map.items():
                if device.ip is not None:
                    hosts.add((name, device.ip))
                elif device.dns_hostname is not None:
                    hosts.add((name, device.dns_hostname))

            # Ideally, don't block on this. Leaving the scope waits for all threads to finish.
            for name, is_online in _ping_in_parallel(hosts):
                db_interface.add_pet_availability(name, is_online)


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    settings = get_settings()
    if settings.pinger_settings is None:
        print("Pinger settings not found.")
        return

    DBInterface.set_hard_coded_pet_interfaces(settings.hard_coded_pet_interfaces)
    stop_condition = Condition()
    pinger = Pinger(stop_condition, settings.pinger_settings)
    run_services(stop_condition, [pinger])


if __name__ == '__main__':
    main()
