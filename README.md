https://code.visualstudio.com/docs/python/tutorial-django
https://www.fusionbox.com/blog/detail/creating-conditionally-required-fields-in-django-forms/577/


https://github.com/Choices-js/Choices


https://testdriven.io/blog/django-htmx-tailwind/
https://vaaibhavsharma.medium.com/unlocking-the-magic-of-single-page-applications-with-django-and-htmx-f0ba8d93be11


```
python manage.py makemigrations
python manage.py migrate
python manage.py runserver

python -m pet_monitor.pet_monitor_service


```

http://127.0.0.1:8000/
http://127.0.0.1:8000/view_relationships
http://127.0.0.1:8000/view_history


# Discovery

- Router - MAC + IP + Hostname(DHCP) + Description(Static route table)
- ARP+PING - MAC + IP 
- NMAP - MAC(If on same LAN segment) + IP + Hostname(DNS)
- mDNS (avahi-browse / avahi-resolve) - MAC + IP
# Scanning

- IP -> host: nslookup
- host -> IP: dig / socket.gethostbyname
- IP -> MAC/hostname/services: nmap
- MAC <-> IP: arp 


# TODO
When pihole 6 is released, add integration into pihole API
Handle case where device has mutliple NIC's
Add mDNS + bespoke advertisement of device info
Add pet conversations
Chat bubbles for pet conversations
Identifiers, host, MAC, mDNS?
Figure out sensors for each device (ping, http, custom, SNMP)
Any way to better abstract the router info dump?
Add more stuff to relationship view, like moods as a color with legend
Add different mood algorithms
Make relationship logic more involved
Have paginated view of activity in reverse chronological order
Log Django errors
