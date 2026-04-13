# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Deploy stage (copy built files into shared volume) ----
# Runs as root because the gui-dist Docker volume is root-owned.
# This is an ephemeral container that exits after copying — no security concern.
FROM alpine:3.20
RUN mkdir -p /gui-dist
COPY --from=build /app/build /gui-build
CMD ["sh", "-c", "rm -rf /gui-dist/* && cp -r /gui-build/* /gui-dist/ && echo 'GUI deployed to /gui-dist'"]
