#!/usr/bin/env bash

set -x 
set -e 

rm -rf kit-app/_*
(cd kit-app && ./build.sh)
(cd kit-app && ./repo.sh package)
docker compose build --no-cache