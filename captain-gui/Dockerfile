# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Deploy stage (copy built files into shared volume) ----
FROM alpine:3.20
RUN addgroup -S appuser && adduser -S appuser -G appuser \
    && mkdir -p /gui-dist && chown appuser:appuser /gui-dist
COPY --from=build --chown=appuser:appuser /app/build /gui-build
USER appuser
CMD ["sh", "-c", "rm -rf /gui-dist/* && cp -r /gui-build/* /gui-dist/ && echo 'GUI deployed to /gui-dist'"]
