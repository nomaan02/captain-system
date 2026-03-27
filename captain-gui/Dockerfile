# Stage 1: Build React SPA
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Copy built files to volume on every container start
# This ensures the gui-dist volume always gets fresh files after a rebuild.
FROM alpine:3.19
COPY --from=build /app/dist /gui-staging
CMD ["sh", "-c", "rm -rf /gui-dist/* 2>/dev/null; cp -r /gui-staging/* /gui-dist/ && echo 'GUI files deployed to volume'"]
