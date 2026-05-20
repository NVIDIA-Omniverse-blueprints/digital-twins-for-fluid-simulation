FROM node:lts-bookworm-slim AS kit-streamer

WORKDIR /kit-streamer

COPY kit-streamer/.npmrc kit-streamer/package.json kit-streamer/package-lock.json ./
RUN npm ci --ignore-scripts

COPY kit-streamer/index.js kit-streamer/vite.config.js ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY trame-app/requirements.txt .
COPY trame-app/static/ ./static/
COPY --from=kit-streamer /trame-app/static/kit-streamer.iife.js ./static/kit-streamer.iife.js
COPY trame-app/app.py .
COPY trame-app/setup-trame.sh .
RUN chmod +x setup-trame.sh && ./setup-trame.sh

# The app always listens on port 5173 inside the container.
# Use WEB_HOST_PORT in compose.yml to control the host-side mapping.
EXPOSE 5173
CMD ["/app/.venv/bin/python", "app.py", "--port", "5173", "--server"]
