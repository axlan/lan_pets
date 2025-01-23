import base64
import logging
import os
import re
import time
from datetime import UTC, date, datetime
from pathlib import Path
from random import randrange
from typing import Optional
from zoneinfo import ZoneInfo

from django.http import HttpResponseNotFound, HttpResponseServerError
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from avatar_gen.generate_avatar import get_pet_avatar
from manage_pets.models import PetData
from pet_monitor.common import CONSOLE_LOG_FILE, get_timestamp_age_str
from pet_monitor.network_scanner import NetworkScanner
from pet_monitor.pet_ai import PetAi
from pet_monitor.ping import Pinger
from pet_monitor.settings import get_settings
from pet_monitor.tplink_scraper.scraper import TrafficStats

logger = logging.getLogger(__name__)

_REPO_PATH = Path(__file__).parents[1].resolve()
_STATIC_PATH = _REPO_PATH / 'data/static'
os.makedirs(_STATIC_PATH, exist_ok=True)

_MONITOR_SETTINGS = get_settings()

_MAX_LOG_HISTORY_BYTES = 1024 * 32

greetings = [line.strip() for line in open('data/greetings.txt').readlines()]


@csrf_exempt
def manage_pets(request):
    if request.method == "POST":
        name = request.POST.get('pet-name')
        id_type = PetData.PrimaryIdentifier[request.POST.get('id-type')]
        device_type = PetData.DeviceType[request.POST.get('device-type')]
        pet_id = request.POST.get('pet-id')
        logger.info(f'Adding pet [name={name}, id_type={id_type}, id={pet_id}]')
        PetData.objects.create(name=name, identifier_type=id_type, identifier_value=pet_id, device_type=device_type)

    pets = list(PetData.objects.iterator())
    scanner = NetworkScanner(_MONITOR_SETTINGS)
    discovered_devices = scanner.get_discovered_devices()
    mapped_pets = scanner.map_pets_to_devices(discovered_devices, pets)
    last_seen_timestamps = Pinger(_MONITOR_SETTINGS.pinger_settings).load_last_seen([p.name for p in pets])

    #     friend_rows = '''\
    # ["Nala", "Happy", "^._.^"],
    # ["Rail Blazer", "Sad", "Hi"]
    # '''
    friend_rows = []
    pet_ai = PetAi(_MONITOR_SETTINGS.pet_ai_settings)
    for pet in PetData.objects.iterator():
        device = mapped_pets[pet.name]
        timestamp = last_seen_timestamps[pet.name]
        # Remove from list so they don't show up twice time.
        if device in discovered_devices:
            discovered_devices.remove(device)
        mac_address = device.mac
        avatar_path = get_pet_avatar(_STATIC_PATH, pet.device_type, pet.name, mac_address)
        mood = pet_ai.get_moods([pet.name])[pet.name].name
        friend_rows.append(
            f'["{pet.name}", "{get_timestamp_age_str(timestamp, now_interval=60)}", "{mood.title()}", "{greetings[randrange(len(greetings))]}", "{pet.device_type}", "{avatar_path.name}"]')
    friend_rows = ',\n'.join(friend_rows)

    # Format scraper results into JS table.
    router_rows = ''
    rows = []
    for device in discovered_devices:
        client_name = device.dns_hostname if device.dhcp_name is None else device.dhcp_name
        record = [client_name, device.get_timestamp_age_str(now_interval=10*60), device.router_description, device.ip, device.mac]
        values = ['"?"' if r is None else f'"{r}"' for r in record]
        values = ",".join(values)
        rows.append(f'[{values}]')
    router_rows = ',\n'.join(rows)

    return render(request, "manage_pets/manage_pets.html",
                  {'friend_rows': friend_rows, "router_results_exist": True, "router_rows": router_rows})


def view_relationships(request):
    names:set[str] = set()
    icons:dict[str, str] = {}
    pets = list(PetData.objects.iterator())
    scanner = NetworkScanner(_MONITOR_SETTINGS)
    mapped_pets = scanner.map_pets_to_devices(scanner.get_discovered_devices(), pets)
    for pet in pets:
        names.add(pet.name)
        mac_address = mapped_pets[pet.name].mac
        icons[pet.name] = get_pet_avatar(_STATIC_PATH, pet.device_type, pet.name, mac_address).name

    pet_ai = PetAi(_MONITOR_SETTINGS.pet_ai_settings)
    relationships = pet_ai.get_all_relationships()
    pet_data = {(n, pet_ai.get_moods(names)[n].name.lower(), icons[n]) for n in names}
    relationships = {(r[0], r[1], r[2].name.lower(), ) for r in relationships}
    return render(request, "manage_pets/view_relationships.html", {'pet_data': pet_data,
                                                                   'relationships': relationships, })


def view_data_usage(request):
    pets = list(PetData.objects.iterator())
    scanner = NetworkScanner(_MONITOR_SETTINGS)
    tplink_scraper = scanner.tplink_scraper
    history_start_time = time.time() - _MONITOR_SETTINGS.plot_data_window_sec
    
    if tplink_scraper is None:
        return HttpResponseServerError('<h1>Bandwidth Usage Not Available. Add Router Info to Settings.</h1>')

    mapped_pets = scanner.map_pets_to_devices(scanner.get_discovered_devices(), pets)
    mac_addresses = [m.mac for m in mapped_pets.values() if m.mac is not None]
    traffic_stats = tplink_scraper.load_mean_bps(mac_addresses, since_timestamp=history_start_time)
    device_types = {p.name:p.device_type for p in pets}

    pet_data = []

    max_bytes = 1
    for name, info in mapped_pets.items():
        if info.mac is not None and info.mac in traffic_stats:
            max_bytes = max(max_bytes, traffic_stats[info.mac].rx_bytes, traffic_stats[info.mac].tx_bytes)

    for name, info in mapped_pets.items():
        available =  info.mac in traffic_stats
        rx_bytes = 0
        tx_bytes = 0
        if info.mac is not None and available:
            rx_bytes = int(traffic_stats[info.mac].rx_bytes)
            tx_bytes = int(traffic_stats[info.mac].tx_bytes)
        larger_byte_val = max(rx_bytes, tx_bytes)
        max_bytes = max(max_bytes, larger_byte_val)
        pet_data.append((
            name,
            available,
            rx_bytes,
            tx_bytes,
            larger_byte_val / max_bytes * 100.0,
            get_pet_avatar(_STATIC_PATH, device_types[name], name, info.mac).name  
        ))
    pet_data = sorted(pet_data, key=lambda x: x[4], reverse=True)

    return render(request, "manage_pets/view_data_usage.html", {'pet_data': pet_data})


@csrf_exempt
def view_pet(request, name):
    matching_objects = PetData.objects.filter(name__exact=name)
    if len(matching_objects) == 0:
        return HttpResponseNotFound(f'<h1>Pet "{name}" Not Found</h1>')
    else:
        pinger = Pinger(_MONITOR_SETTINGS.pinger_settings)
        pet_ai = PetAi(_MONITOR_SETTINGS.pet_ai_settings)
        pet_data = matching_objects[0]
        scanner = NetworkScanner(_MONITOR_SETTINGS)
        tplink_scraper = scanner.tplink_scraper
        mapped_pets = scanner.map_pets_to_devices(scanner.get_discovered_devices(), [pet_data])
        device_data = mapped_pets[name]
        avatar_path = get_pet_avatar(_STATIC_PATH, pet_data.device_type, name, device_data.mac)
        history_start_time = time.time() - _MONITOR_SETTINGS.plot_data_window_sec
        if tplink_scraper is None or device_data.mac is None:
            tp_link_traffic_info = TrafficStats(0, 0, 0, 0, 0)
            traffic_data_webp = None
        else:
            tp_link_traffic_info = tplink_scraper.load_mean_bps([device_data.mac]).get(
                device_data.mac, TrafficStats(0, 0, 0, 0, 0))
            traffic_data_webp = base64.b64encode(tplink_scraper.generate_traffic_plot(
                device_data.mac, since_timestamp=history_start_time)).decode('utf-8')
        mean_uptime = pinger.load_availability_mean([pet_data.name],
                                                    since_timestamp=history_start_time).get(pet_data.name)
        relationships = pet_ai.get_relationships([pet_data.name]).get_relationships(pet_data.name)
        relationships = {n: m.name for n, m in relationships.items()}
        mood = pet_ai.get_moods([pet_data.name])[pet_data.name]
        up_time_webp = base64.b64encode(
            pinger.generate_uptime_plot(
                pet_data.name,
                since_timestamp=history_start_time)).decode('utf-8')

        if pet_data.description is not None:
            substitute_ip = 'IP_UNKNOWN' if device_data.ip is None else device_data.ip
            description = pet_data.description.replace('{IP}', substitute_ip)
        else:
            description = None

        return render(request, "manage_pets/view_pet.html", {'pet_data': pet_data,
                                                             'description': description,
                                                             'device_info': device_data,
                                                             'mood': mood.name,
                                                             'relationships': relationships,
                                                             'traffic_info': tp_link_traffic_info,
                                                             'traffic_data_webp': traffic_data_webp,
                                                             'mean_uptime': mean_uptime,
                                                             'up_time_webp': up_time_webp,
                                                             'avatar_path': avatar_path.name, })


@csrf_exempt
def delete_pet(request, name):
    matching_objects = PetData.objects.filter(name__exact=name)
    for pet in matching_objects:
        pet.delete()

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
    matching_objects = PetData.objects.filter(name__exact=name)
    if len(matching_objects) == 0:
        return HttpResponseNotFound(f'<h1>Pet "{name}" Not Found</h1>')
    else:
        pet_data = matching_objects[0]
        if request.method == "POST":
            description = request.POST.get('pet-description')
            pet_data.description = description
            pet_data.save()
            return redirect("/view_pet/" + name)
        else:
            return render(request, "manage_pets/edit_pet.html", {'pet_data': pet_data})
