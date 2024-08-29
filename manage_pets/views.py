import re
from django.utils.timezone import datetime
from django.http import HttpResponse
from django.shortcuts import render

from django.shortcuts import redirect
from manage_pets.forms import LogMessageForm
from manage_pets.models import PetData
from django.http import HttpResponseRedirect


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
