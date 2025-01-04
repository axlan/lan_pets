#!/usr/bin/env sh

gunicorn --bind 0.0.0.0:8000 lan_pets.wsgi&

python -m pet_monitor.pet_monitor_service&

wait
