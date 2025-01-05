#!/usr/bin/env bash

docker build -t lan-pets-python .
docker rm -f lan-pets
docker run -itd --restart=always -p 8000:8000 -v $(pwd)/data:/app/data --name lan-pets lan-pets-python
