#!/usr/bin/env bash

set -x 
set -e 

# Build kit components using top-level build script
../build-all.sh

# Build the web app
(cd ../web-app && npm install)