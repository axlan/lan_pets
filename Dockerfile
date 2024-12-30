FROM python:3.13
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY avatar_gen /app/avatar_gen
COPY lan_pets /app/lan_pets
COPY manage_pets /app/manage_pets
COPY pet_monitor /app/pet_monitor
COPY scripts /app/scripts

CMD ["/app/scripts/run_servers.sh"]
