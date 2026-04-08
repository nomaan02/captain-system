# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Deploy stage (copy built files into shared volume) ----
FROM alpine:3.20
COPY --from=build /app/build /gui-build
CMD ["sh", "-c", "rm -rf /gui-dist/* && cp -r /gui-build/* /gui-dist/ && echo 'GUI deployed to /gui-dist'"]
