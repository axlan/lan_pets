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

TODO:
Identifiers, host, MAC, mDNS?
Figure out sensors for each device (ping, http, custom, SNMP)
Any way to better abstract the router info dump?
Add header with links to manage pets and relationships
Add more stuff to relationship view, like moods as a color with legend
Add different mood algorithms
Chat bubbles for messages
Make relationship logic more involved
Create log of activity
Have paginated view of activity in reverse chronological order


2025-01-01 07:29:57,753 - pet_monitor.pet_ai - INFO - Zephurus went from SHY to MODEST
2025-01-01 07:29:57,760 - pet_monitor.pet_ai - INFO - Friendship between Zephurus and Pixel 8
2025-01-01 07:29:57,770 - pet_monitor.pet_ai - INFO - Pixel 8 went from IMPISH to MODEST
2025-01-01 07:30:28,364 - pet_monitor.pet_ai - INFO - Zephurus went from MODEST to SNEAKY
2025-01-01 07:30:28,371 - pet_monitor.pet_ai - INFO - Breaking up Zephurus and Pixel 8
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/workspaces/lan_pets/pet_monitor/pet_monitor_service.py", line 104, in <module>
    main()
  File "/workspaces/lan_pets/pet_monitor/pet_monitor_service.py", line 98, in main
    pet_ai.update(mood_data)
  File "/workspaces/lan_pets/pet_monitor/pet_ai.py", line 151, in update
    all_relationships[breakup_name].pop(name)
KeyError: 'Zephurus'
