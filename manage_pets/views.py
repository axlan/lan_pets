import logging
import os
from random import randrange

from django.utils.timezone import datetime
from django.http import HttpResponse
from django.shortcuts import render

from django.shortcuts import redirect
from manage_pets.forms import LogMessageForm
from manage_pets.models import PetData
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

import sqlite3

logger = logging.getLogger(__name__)

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

greetings = [line.strip() for line in open('data/greetings.txt').readlines()]

@csrf_exempt
def manage_pets(request):
    if request.method == "POST":
        name = request.POST.get('pet-name')
        id_type = PetData.PrimaryIdentifier[request.POST.get('id-type')]
        pet_id = request.POST.get('pet-id')
        logger.info(f'Adding pet [name={name}, id_type={id_type}, id={pet_id}]')
        if id_type == PetData.PrimaryIdentifier.MAC:
            PetData.objects.create(name=name, identifier_type=id_type, mac_address=pet_id)
        else:
            raise NotImplementedError('Only MAC supported.')

    #     friend_rows = '''\
    # ["Nala", "Happy", "^._.^"],
    # ["Rail Blazer", "Sad", "Hi"]
    # '''
    friend_rows = []
    for pet in PetData.objects.iterator():
        friend_rows.append(f'["{pet.name}", "Happy", "{greetings[randrange(len(greetings))]}"]')
    friend_rows = ',\n'.join(friend_rows)

    router_db = "data/tp_clients.sqlite3"
    router_results_exist = False
    router_rows = ''
    if os.path.exists(router_db):
        # Read sqlite query results into a pandas DataFrame
        with sqlite3.connect(router_db) as con:
            cur = con.cursor()
            cur.execute("SELECT client_name, description, ip, mac FROM client_info")
            rows = []
            for record in cur.fetchall():
                values = ['"?"' if r is None else f'"{r}"' for r in record]
                values = ",".join(values)
                rows.append(f'[{values}]')
        router_rows = ',\n'.join(rows)
        router_results_exist = True

    return render(request, "manage_pets/manage_pets.html", {'friend_rows': friend_rows, "router_results_exist": router_results_exist, "router_rows": router_rows})

@csrf_exempt
def view_pet(request, name):
    matching_objects  = PetData.objects.filter(name__contains=name)
    if len(matching_objects) == 0:
        return "Not Found"
    else:
        return render(request, "manage_pets/show_pet.html", {'pet_name': matching_objects[0].name})

@csrf_exempt
def delete_pet(request, name):
    matching_objects  = PetData.objects.filter(name__contains=name)
    for pet in matching_objects:
        pet.delete()
    
    return redirect('/manage_pets')

