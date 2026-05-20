FROM nginx:1.27-alpine

RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/nginx.conf
COPY entrypoint.sh /entrypoint.sh

RUN chmod 555 /entrypoint.sh && \
    mkdir -p /etc/nginx/tls

ENTRYPOINT ["/entrypoint.sh"]
