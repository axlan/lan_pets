import os
from django.utils.timezone import datetime
from django.http import HttpResponse
from django.shortcuts import render

from django.shortcuts import redirect
from manage_pets.forms import LogMessageForm
from manage_pets.models import PetData
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

import sqlite3

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
    
    friend_rows = '''\
["Nala", "Happy", "^._.^"],
["Rail Blazer", "Sad", "Hi"]
'''

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
