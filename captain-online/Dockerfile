FROM python:3.11-slim

# System deps for psycopg2-binary and timezone
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application code (invalidated by any code change)
COPY . .

ENV PYTHONUNBUFFERED=1
ENV TZ=America/New_York

# Health check: verify main process is alive and can reach QuestDB.
# Avoids Python subprocess — WSL2 memory corruption causes random segfaults.
# curl QuestDB's HTTP health endpoint from inside this container.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -sf http://questdb:9000/exec?query=SELECT%201 || exit 1

CMD ["python", "-m", "captain_online.main"]
