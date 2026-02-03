#!/usr/bin/env bash
set -xe

# change dir to location of this script file.
cd "$(dirname "$0")"

docker compose build --no-cache

# Remind user to copy .env
if [ ! -f .env ] ; then
  echo "WARNING: Please ensure you copy .env_template to .env before running"
fi
