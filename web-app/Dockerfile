# Stage 1 - build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build          # produces /app/dist with hashed assets

# Stage 2 - serve
FROM nginx:1.27-alpine
# Copy the built site
COPY --from=build /app/dist/ /usr/share/nginx/html/
# Replace the default server config with our cache-aware one
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
