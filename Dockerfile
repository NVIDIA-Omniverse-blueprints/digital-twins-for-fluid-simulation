# =============================================================================
# Multi-stage Dockerfile for the Digital Twins for Fluid Simulation kit app.
#
# Stages:
#   base  — shared OS setup (apt packages) inherited by both build and final
#   build — compiles and packages the kit app, then discards build artifacts
#   final — minimal runtime image; receives only the unpacked app from build
#
# The multi-stage approach keeps the final image small: compiler toolchain,
# source tree, and packman cache are all left behind in the build stage.
# =============================================================================

# -----------------------------------------------------------------------------
# base: install OS packages needed by both the build and runtime environments.
# Using a named stage avoids duplicating the apt setup in the final stage.
# -----------------------------------------------------------------------------
FROM nvcr.io/nvidia/omniverse/ov-base-ubuntu-22:2025.2.0 AS base
USER root
RUN echo "deb https://archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://archive.ubuntu.com/ubuntu/ jammy-updates main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://archive.ubuntu.com/ubuntu/ jammy-backports main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://security.ubuntu.com/ubuntu jammy-security main restricted universe multiverse" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y git git-lfs build-essential libunwind8 && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# -----------------------------------------------------------------------------
# build: compile, package, and unpack the kit app.
# The source tree is copied in, built via repo.sh, and the resulting zip is
# unpacked into ./package.  Build artifacts (_build, _repo, packman cache) are
# then removed so they are not carried into the final image via COPY --from.
# -----------------------------------------------------------------------------
FROM base AS build
RUN chown -R ubuntu:ubuntu /home/ubuntu/
COPY --chown=ubuntu:ubuntu . /home/ubuntu/source

USER ubuntu
WORKDIR /home/ubuntu/source

RUN ./repo.sh build -r && \
    ./repo.sh package -c release && \
    PACKAGE_FILE=$(find _build/packages -type f -name "*.zip") && \
    mkdir -p ./package && \
    unzip -q $PACKAGE_FILE -d ./package && \
    # Remove packman download cache and all build/repo artifacts to keep
    # the layer small — only ./package is needed by the final stage.
    rm -rf ~/packman-repo && \
    rm -rf _* && \
    rm -rf kit-cae/_*


# -----------------------------------------------------------------------------
# final: minimal runtime image.
# Inherits OS packages from `base` and receives only the unpacked app from the
# build stage.  No compiler, no source, no build cache.
# -----------------------------------------------------------------------------
FROM base

USER root
# Pre-create Omniverse cache and USD directories expected at runtime.
RUN mkdir -p /home/ubuntu/.cache/ov && \
    mkdir -p /home/ubuntu/.local/share/ov && \
    mkdir -p /home/ubuntu/usd && \
    mkdir -p /home/ubuntu/.cache/warp

RUN chown -R ubuntu:ubuntu /home/ubuntu/.cache && \
    chown -R ubuntu:ubuntu /home/ubuntu/.local

WORKDIR /scripts
COPY scripts/startup.sh /scripts/startup.sh

WORKDIR /app
COPY --from=build /home/ubuntu/source/package /app

USER ubuntu
# Ports used by Omniverse live-streaming (WebRTC, signalling, and web UI).
EXPOSE 47995-48012/udp \
       47995-48012/tcp \
       49000-49007/udp \
       49000-49007/tcp \
       8011/tcp \
       8111/tcp \
       49100/tcp

ENTRYPOINT ["/scripts/startup.sh"]
