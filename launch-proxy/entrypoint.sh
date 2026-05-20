#!/bin/sh
# Launch-proxy container entrypoint.
#
# Ensures TLS material exists before starting nginx. If /etc/nginx/tls is empty
# (the default for local/dev runs) a self-signed cert is generated in place so
# the :443 listener in nginx.conf can come up. To use a real certificate,
# mount cert.pem + key.pem into /etc/nginx/tls/ and this step is skipped.
set -eu

if [ ! -f /etc/nginx/tls/cert.pem ] || [ ! -f /etc/nginx/tls/key.pem ]; then
  # 10-year self-signed cert, CN=localhost — fine for dev; browsers will warn.
  # `-nodes` leaves the key unencrypted so nginx can read it without a passphrase.
  openssl req \
    -x509 \
    -newkey rsa:4096 \
    -keyout /etc/nginx/tls/key.pem \
    -out /etc/nginx/tls/cert.pem \
    -sha256 \
    -days 3650 \
    -nodes \
    -subj "/C=US/ST=CA/L=Santa Clara/O=NVIDIA/OU=RTDT/CN=localhost"
fi

# `daemon off` keeps nginx in the foreground so the container's PID 1 is nginx
# itself — signals (SIGTERM on `docker stop`) reach it directly.
exec nginx -g "daemon off;"
