#!/usr/bin/env bash

# (Re)Build the image.
docker build -t lan-pets-python .

# Stop and remove the container if it exists.
docker rm -f lan-pets 2> /dev/null

# The `--restart=always` flag will make this container restart if it crashes, and whenever the Docker daemon start
# (usually on system boot).
# The use of `--net=host --privileged` is needed to allow NMAP to efficiently scan the LAN.
# If a bridge network is used, the HTTP port must be published (e.x. `-p 8000:8000`).
# State is written to `/app/data` which also expects the presence of the data files in this repo.
docker run -itd --restart=always --net=host --privileged \
   -v $(pwd)/data:/app/data --name lan-pets lan-pets-python
