#!/usr/bin/env bash
set -xe

# change dir to location of this script file.
cd "$(dirname "$0")"

# fetch kit-cae if not already present
rm -rf kit-cae
echo "Fetching kit-cae repository..."
curl -L -o kit-cae.tar.xz  "https://github.com/NVIDIA-Omniverse/kit-cae/archive/refs/tags/v1.5.0.tar.gz"
mkdir -p kit-cae
tar -xf kit-cae.tar.xz -C kit-cae --strip-components=1

pushd kit-cae

echo "Building kit-cae..."
./repo.sh schema --clean
./repo.sh build -rx
./repo.sh package --thin

# read filename from ./_build/packages/*+latest.txt
THIN_PACKAGE_FILE=$(cat ./_build/packages/*+latest.txt)
echo "Thin package file: $THIN_PACKAGE_FILE"
# extract package to ./_install using zip
rm -rf ./_install
mkdir -p ./_install
unzip -q "./_build/packages/$THIN_PACKAGE_FILE" -d ./_install
popd  # kit-cae

pushd kit-app
echo "Building kit-app..."
./repo.sh build -rx
./repo.sh package -c release
popd  # kit-app