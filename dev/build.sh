#!/usr/bin/env bash

set -x 
set -e 

(cd ../kit-app && ./build.sh)
(cd ../web-app; npm install)