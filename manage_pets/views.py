import base64
import logging
import os
import time
from pathlib import Path
from random import randrange

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.timezone import datetime
from django.views.decorators.csrf import csrf_exempt

from avatar_gen.generate_avatar import get_pet_avatar
from manage_pets.forms import LogMessageForm
from manage_pets.models import PetData
from pet_monitor.pet_ai import PetAi
from pet_monitor.ping import Pinger
from pet_monitor.settings import get_settings
from pet_monitor.tplink_scraper.scraper import (ClientInfo, TPLinkScraper,
                                                TrafficStats)

logger = logging.getLogger(__name__)

_REPO_PATH = Path(__file__).parents[1].resolve()
_STATIC_PATH = _REPO_PATH / 'data/static'
os.makedirs(_STATIC_PATH, exist_ok=True)

_MONITOR_SETTINGS = get_settings()

greetings = [line.strip() for line in open('data/greetings.txt').readlines()]


def _load_client_info(tplink_scraper):
    tp_link_info = _MONITOR_SETTINGS.hard_coded_client_info()
    if tplink_scraper:
        tp_link_info.update(tplink_scraper.load_info())
    return tp_link_info


def home(request):
    return HttpResponse("Hello, Django!")


def hello_there(request, name):
    form = LogMessageForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        message = form.save(commit=False)
        message.log_date = datetime.now()
        message.save()
        return redirect("home")
    else:
        return render(request, "manage_pets/hello_there.html", {"form": form})


@csrf_exempt
def manage_pets(request):
    if request.method == "POST":
        name = request.POST.get('pet-name')
        id_type = PetData.PrimaryIdentifier[request.POST.get('id-type')]
        device_type = PetData.DeviceType[request.POST.get('device-type')]
        pet_id = request.POST.get('pet-id')
        logger.info(f'Adding pet [name={name}, id_type={id_type}, id={pet_id}]')
        if id_type == PetData.PrimaryIdentifier.MAC:
            PetData.objects.create(name=name, identifier_type=id_type, mac_address=pet_id, device_type=device_type)
        else:
            raise NotImplementedError('Only MAC supported.')

    #     friend_rows = '''\
    # ["Nala", "Happy", "^._.^"],
    # ["Rail Blazer", "Sad", "Hi"]
    # '''
    friend_rows = []
    pet_ai = PetAi(_MONITOR_SETTINGS.pet_ai_settings)
    for pet in PetData.objects.iterator():
        avatar_path = get_pet_avatar(_STATIC_PATH, pet.device_type, pet.mac_address)
        mood = pet_ai.get_moods([pet.name])[pet.name].name
        friend_rows.append(
            f'["{pet.name}", "{mood.title()}", "{greetings[randrange(len(greetings))]}", "{avatar_path.name}"]')
    friend_rows = ',\n'.join(friend_rows)

    # Format scraper results into JS table.
    tplink_scraper = None if _MONITOR_SETTINGS.tplink_settings is None else TPLinkScraper(
        _MONITOR_SETTINGS.tplink_settings)
    router_results_exist = tplink_scraper is not None or len(_MONITOR_SETTINGS.hard_coded_clients) > 0
    router_rows = ''
    if router_results_exist:
        rows = []
        tp_link_info = _load_client_info(tplink_scraper)
        for info in tp_link_info.values():
            record = [info.client_name, info.description, info.ip, info.mac]
            values = ['"?"' if r is None else f'"{r}"' for r in record]
            values = ",".join(values)
            rows.append(f'[{values}]')
        router_rows = ',\n'.join(rows)

    return render(request, "manage_pets/manage_pets.html",
                  {'friend_rows': friend_rows, "router_results_exist": router_results_exist, "router_rows": router_rows})


def view_relationships(request):
    names = {pet.name for pet in PetData.objects.iterator()}
    pet_ai = PetAi(_MONITOR_SETTINGS.pet_ai_settings)
    relationships = pet_ai.get_all_relationships()
    pet_data = {(n, pet_ai.get_moods(names)[n].name.lower()) for n in names}
    relationships = {(r[0], r[1], r[2].name.lower()) for r in relationships}
    return render(request, "manage_pets/view_relationships.html", {'pet_data': pet_data,
                                                                   'relationships': relationships, })


@csrf_exempt
def view_pet(request, name):
    matching_objects = PetData.objects.filter(name__exact=name)
    if len(matching_objects) == 0:
        return "Not Found"
    else:
        pinger = Pinger(_MONITOR_SETTINGS.pinger_settings)
        pet_ai = PetAi(_MONITOR_SETTINGS.pet_ai_settings)
        tplink_scraper = None if _MONITOR_SETTINGS.tplink_settings is None else TPLinkScraper(
            _MONITOR_SETTINGS.tplink_settings)
        pet_data = matching_objects[0]
        avatar_path = get_pet_avatar(_STATIC_PATH, pet_data.device_type, pet_data.mac_address)
        history_start_time = time.time() - _MONITOR_SETTINGS.plot_data_window_sec
        tp_link_info = _load_client_info(tplink_scraper).get(pet_data.mac_address, ClientInfo('Unknown'))
        if tplink_scraper is None:
            tp_link_traffic_info = TrafficStats(0, 0, 0, 0, 0)
            traffic_data_webp = base64.b64encode(open(_STATIC_PATH / 'no_data.webp', 'rb').read()).decode('utf-8')
        else:
            tp_link_traffic_info = tplink_scraper.load_mean_bps([pet_data.mac_address]).get(
                pet_data.mac_address, TrafficStats(0, 0, 0, 0, 0))
            traffic_data_webp = base64.b64encode(tplink_scraper.generate_traffic_plot(
                pet_data.mac_address, since_timestamp=history_start_time)).decode('utf-8')
        mean_uptime = pinger.load_availability_mean([pet_data.name],
                                                    since_timestamp=history_start_time).get(pet_data.name)
        relationships = pet_ai.get_relationships([pet_data.name])[pet_data.name]
        relationships = {n: m.name for n, m in relationships.items()}
        mood = pet_ai.get_moods([pet_data.name])[pet_data.name]
        up_time_webp = base64.b64encode(
            pinger.generate_uptime_plot(
                pet_data.name,
                since_timestamp=history_start_time)).decode('utf-8')

        return render(request, "manage_pets/show_pet.html", {'pet_data': pet_data,
                                                             'router_info': tp_link_info,
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


def edit_pet(request, name):
    matching_objects = PetData.objects.filter(name__exact=name)
    if len(matching_objects) == 0:
        return "Not Found"
    else:
        pet_data = matching_objects[0]
        if request.method == "POST":
            description = request.POST.get('pet-description')
            pet_data.description = description
            pet_data.save()
            return redirect("/view_pet/" + name)
        else:
            return render(request, "manage_pets/edit_pet.html", {'pet_data': pet_data})
