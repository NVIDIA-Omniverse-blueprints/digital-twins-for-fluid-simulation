#!/usr/bin/env bash

set -x 
set -e 

# Ensure omni.cgns is copied to the build directory before the main build
mkdir -p _build/linux-x86_64/release/exts/omni.cgns
cp -r source/extensions/omni.cgns/* _build/linux-x86_64/release/exts/omni.cgns/

mkdir -p _build/linux-x86_64/release/exts/omni.usd.fileformat.cgns
cp -r source/extensions/omni.usd.fileformat.cgns/* _build/linux-x86_64/release/exts/omni.usd.fileformat.cgns/

# Now run the main build
(./repo.sh build -r --verbose)
