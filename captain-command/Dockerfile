FROM python:3.12-slim

# System deps for psycopg2-binary, timezone, and health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata curl git \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI + Compose plugin (for git-pull rebuild feature)
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
    | tar xz -C /usr/local/bin --strip-components=1 docker/docker \
    && mkdir -p /usr/local/lib/docker/cli-plugins \
    && curl -fsSL "https://github.com/docker/compose/releases/download/v2.35.1/docker-compose-linux-x86_64" \
       -o /usr/local/lib/docker/cli-plugins/docker-compose \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

WORKDIR /app

# Install Python deps first (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application code (invalidated by any code change)
COPY . .

# Bake config into image (avoids WSL2 9p bind-mount issues)
COPY _config/ /captain/config/

ENV PYTHONUNBUFFERED=1
ENV TZ=America/New_York

# Health check: FastAPI /api/health verifies Redis+QuestDB connectivity internally.
# Avoid Python subprocess — WSL2 memory corruption causes random segfaults in short-lived interpreters.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -sf http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "captain_command.main"]
