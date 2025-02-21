import base64
import logging
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path
from random import randrange
from typing import Optional
from zoneinfo import ZoneInfo

from django.http import HttpResponseNotFound, HttpResponseServerError
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from avatar_gen.generate_avatar import get_pet_avatar
from pet_monitor.common import (
    CONSOLE_LOG_FILE,
    DeviceType,
    IdentifierType,
    ExtraNetworkInfoType,
    PetInfo,
    Relationship,
    TrafficStats,
    get_device_name,
    get_device_summary,
    get_timestamp_age_str,
    map_pets_to_devices,
    sizeof_fmt,
    get_cutoff_timestamp
)
from pet_monitor.network_db import DBInterface
from pet_monitor.settings import get_settings

logger = logging.getLogger(__name__)

_REPO_PATH = Path(__file__).parents[1].resolve()
_STATIC_PATH = _REPO_PATH / 'data/static'
os.makedirs(_STATIC_PATH, exist_ok=True)

_MONITOR_SETTINGS = get_settings()

_MAX_LOG_HISTORY_BYTES = 1024 * 32

greetings = [line.strip() for line in open('data/greetings.txt').readlines()]


@csrf_exempt
def manage_pets(request):
    with DBInterface() as db_interface:
        if request.method == "POST":
            name = request.POST.get('pet-name')
            id_type = IdentifierType[request.POST.get('id-type')]
            device_type = DeviceType[request.POST.get('device-type')]
            pet_id = request.POST.get('pet-id')
            logger.info(f'Adding pet [name={name}, id_type={id_type}, id={pet_id}]')
            db_interface.add_pet_info(PetInfo(
                name=name,
                identifier_type=id_type,
                device_type=device_type,
                identifier_value=pet_id
            ))

        pets = db_interface.get_pet_info()
        discovered_devices = db_interface.get_network_info()
        mapped_pets = map_pets_to_devices(discovered_devices, pets)
        last_seen_timestamps = db_interface.load_last_seen([p.name for p in pets])

        #     friend_rows = '''\
        # ["Nala", "Happy", "^._.^"],
        # ["Rail Blazer", "Sad", "Hi"]
        # '''
        friend_rows = []
        for pet in pets:
            device = mapped_pets[pet.name]
            timestamp = last_seen_timestamps[pet.name]
            # Remove from list so they don't show up twice time.
            if device in discovered_devices:
                discovered_devices.remove(device)
            mac_address = device.mac
            avatar_path = get_pet_avatar(_STATIC_PATH, pet.device_type.name, pet.name, mac_address)
            mood = pet.mood.name
            friend_rows.append(
                f'["{pet.name}", "{get_timestamp_age_str(timestamp, now_interval=60)}", "{mood.title()}", "{greetings[randrange(len(greetings))]}", "{pet.device_type.name}", "{avatar_path.name}"]')
        friend_rows = ',\n'.join(friend_rows)

        # Format scraper results into JS table.
        router_rows = ''
        rows = []
        for device in discovered_devices:
            extra_info = db_interface.get_extra_network_info(device)
            device_description = get_device_summary(extra_info)
            device_name = get_device_name(device, extra_info)

            record = [
                device_name,
                device.get_timestamp_age_str(
                    now_interval=10 * 60),
                device_description,
                device.ip,
                device.mac]
            values = ['"?"' if r is None else f'"{r}"' for r in record]
            values = ",".join(values)
            rows.append(f'[{values}]')
        router_rows = ',\n'.join(rows)

        return render(request, "manage_pets/manage_pets.html",
                    {'friend_rows': friend_rows, "router_results_exist": True, "router_rows": router_rows})


def view_relationships(request):
    with DBInterface() as db_interface:
        icons: dict[str, str] = {}
        pets = db_interface.get_pet_info()
        mapped_pets = db_interface.get_network_info_for_pets(pets)
        for pet in pets:
            mac_address = mapped_pets[pet.name].mac
            icons[pet.name] = get_pet_avatar(_STATIC_PATH, pet.device_type.name, pet.name, mac_address).name

        COLOR_MAP = {
            Relationship.FRIENDS: 'green',
            Relationship.ENEMY: 'red',
        }

        relationships = db_interface.get_all_relationships()
        pet_data = {(p.name, p.mood.name.lower(), icons[p.name]) for p in pets}
        relationships = {(r[0], r[1], COLOR_MAP[r[2]], ) for r in relationships}
        return render(request, "manage_pets/view_relationships.html", {'pet_data': pet_data,
                                                                   'relationships': relationships, })


def view_data_usage(request):
    with DBInterface() as db_interface:
        pets = db_interface.get_pet_info()
        pet_names = tuple(p.name for p in pets)
        device_types = {p.name: p.device_type.name for p in pets}
        pet_interfaces = db_interface.get_network_info_for_pets(pets)

        history_start_time = get_cutoff_timestamp(_MONITOR_SETTINGS.plot_data_window_sec)
        traffic_bps = db_interface.load_bps(pet_names, history_start_time)
        if len(traffic_bps) == 0:
            return HttpResponseServerError('<h1>Bandwidth Usage Not Available. Add Service to Collect Data.</h1>')

        traffic_stats = db_interface.get_mean_traffic(traffic_bps, True)

        pet_data = []

        max_bytes = 1
        for traffic in traffic_stats.values():
            max_bytes = max(max_bytes, traffic.rx_bytes, traffic.tx_bytes)

        for name, info in traffic_stats.items():
            available = info.rx_bytes > 0 or info.tx_bytes > 0
            larger_byte_val = max(info.rx_bytes, info.tx_bytes)
            max_bytes = max(max_bytes, larger_byte_val)
            pet_data.append((
                name,
                available,
                sizeof_fmt(info.rx_bytes),
                sizeof_fmt(info.tx_bytes),
                larger_byte_val / max_bytes * 100.0,
                get_pet_avatar(_STATIC_PATH, device_types[name], name, pet_interfaces[name].mac).name
            ))
        pet_data = sorted(pet_data, key=lambda x: x[4], reverse=True)

        return render(request, "manage_pets/view_data_usage.html", {'pet_data': pet_data})

def _convert_bytes_to_base64(data: Optional[bytes]) -> Optional[str]:
    return None if data is None else base64.b64encode(data).decode('utf-8')

@csrf_exempt
def view_pet(request, name):
    with DBInterface() as db_interface:
        pet = db_interface.get_specific_pet(name)
        if pet is None:
            return HttpResponseNotFound(f'<h1>Pet "{name}" Not Found</h1>')
        else:
            mapped_pets = db_interface.get_network_info_for_pets([pet])
            device_data = mapped_pets[name]
            avatar_path = get_pet_avatar(_STATIC_PATH, pet.device_type.name, name, device_data.mac)
            history_start_time = get_cutoff_timestamp(_MONITOR_SETTINGS.plot_data_window_sec)
            traffic_df = db_interface.load_bps([pet.name], history_start_time)
            if len(traffic_df[name]) > 0:
                traffic_info = db_interface.get_mean_traffic(traffic_df)[name]
                traffic_data_webp = _convert_bytes_to_base64(db_interface.generate_traffic_plot(traffic_df[name]))
            else:
                traffic_data_webp = None
                traffic_info = TrafficStats()

            mean_uptime = db_interface.load_availability_mean([pet.name],
                                                            since_timestamp=history_start_time).get(pet.name)
            up_time_webp = _convert_bytes_to_base64( db_interface.generate_uptime_plot(
                    pet.name,
                    since_timestamp=history_start_time))

            relationships = db_interface.get_relationship_map([pet.name]).get_relationships(pet.name)
            relationships = {n: m.name for n, m in relationships.items()}

            mean_cpu_stats = db_interface.load_cpu_stats_mean([pet.name],
                                                         since_timestamp=history_start_time).get(pet.name)
            cpu_stats_webp =_convert_bytes_to_base64(db_interface.generate_cpu_stats_plot(
                    pet.name,
                    since_timestamp=history_start_time))
            
            extra_info = db_interface.get_extra_network_info(device_data)
            if ExtraNetworkInfoType.MDNS_SERVICES in extra_info:
                services = extra_info[ExtraNetworkInfoType.MDNS_SERVICES].split(',')
            elif ExtraNetworkInfoType.NMAP_SERVICES in extra_info:
                services = extra_info[ExtraNetworkInfoType.NMAP_SERVICES].split(',')
            else:
                services = None

            if pet.description is not None:
                substitute_ip = 'IP_UNKNOWN' if device_data.ip is None else device_data.ip
                description = pet.description.replace('{IP}', substitute_ip)
            else:
                description = None

            return render(request, "manage_pets/view_pet.html", {'pet_data': pet,
                                                                'description': description,
                                                                'device_info': device_data,
                                                                'mood': pet.mood.name,
                                                                'services': services,
                                                                'mean_cpu_stats': mean_cpu_stats,
                                                                'cpu_stats_webp': cpu_stats_webp,
                                                                'relationships': relationships,
                                                                'traffic_info': traffic_info,
                                                                'traffic_data_webp': traffic_data_webp,
                                                                'mean_uptime': mean_uptime,
                                                                'up_time_webp': up_time_webp,
                                                                'avatar_path': avatar_path.name, })


@csrf_exempt
def delete_pet(request, name):
    with DBInterface() as db_interface:
        db_interface.delete_pet_info(name)
        return redirect('/manage_pets')


def view_history(request, name=''):
    if not CONSOLE_LOG_FILE.exists():
        return HttpResponseNotFound(f"<h1>History Log Not Found</h1>")
    file_size = CONSOLE_LOG_FILE.stat().st_size
    history_fd = open(CONSOLE_LOG_FILE, 'r')
    if file_size > _MAX_LOG_HISTORY_BYTES:
        history_fd.seek(file_size - _MAX_LOG_HISTORY_BYTES)
    display_data = ''
    re_timestamp = re.compile(r'^([0-9]+):')
    current_day: Optional[date] = None
    lines = history_fd.readlines()
    lines.reverse()
    for line in lines:
        if len(name) == 0 or name in line:
            m = re_timestamp.search(line)
            if m:
                timestamp = int(m.group(1))
                local_zone = ZoneInfo(_MONITOR_SETTINGS.plot_timezone)
                entry = datetime.fromtimestamp(timestamp, UTC).astimezone(local_zone)
                if current_day is None or (current_day - entry.date()).days > 0:
                    current_day = entry.date()
                    display_data += current_day.strftime('%m/%d/%Y') + '\n'
                line = re_timestamp.sub(entry.strftime('%H:%M:%S:'), line)
            display_data += "  " + line
    return render(request, "manage_pets/view_history.html", {'display_data': display_data})


def edit_pet(request, name):
    with DBInterface() as db_interface:
        pet = db_interface.get_specific_pet(name)
        if pet is not None:
            if request.method == "POST":
                description = request.POST.get('pet-description')
                pet._replace(description=description)
                db_interface.add_pet_info(pet)
                return redirect("/view_pet/" + name)
            else:
                return render(request, "manage_pets/edit_pet.html", {'pet_data': pet})
        else:
            return HttpResponseNotFound(f'<h1>Pet "{name}" Not Found</h1>')
