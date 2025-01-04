#!/usr/bin/env bash

# Kill background jobs when script exits
trap 'kill $(jobs -p)' EXIT

gunicorn --bind 0.0.0.0:8000 lan_pets.wsgi&

python -m pet_monitor.pet_monitor_service&

# Wait for any process to exit
wait -n
