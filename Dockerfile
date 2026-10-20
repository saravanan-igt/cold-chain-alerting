# ==========================================
# Stage 1: Build Next.js Static Export
# ==========================================
FROM node:24-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Python Runtime & FastAPI Server
# ==========================================
FROM python:3.12-slim AS runtime
WORKDIR /app

# Install curl for Docker healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install backend dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code, configuration, and seed dataset
COPY backend/ backend/
COPY config/ config/
COPY starter_kit/ starter_kit/
RUN useradd --system --uid 10001 --home-dir /app coldline && mkdir -p data backups && chown -R coldline:coldline data backups

# Copy static frontend build from Stage 1 into FastAPI mount directory
COPY --from=frontend-builder /app/frontend/out ./frontend/out

# Configuration & Defaults
ENV PYTHONUNBUFFERED=1
ENV COLDCHAIN_DATABASE_URL=data/coldchain.db
ENV COLDCHAIN_CONFIG=config/customers.json
ENV COLDCHAIN_SECURE_COOKIES=1
ENV COLDCHAIN_LOG_FORMAT=json

EXPOSE 8000

USER coldline

# Readiness covers database connectivity and the in-process notification worker.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/ready || exit 1

# Start with configured credentials; never enable demo accounts in the image.
# The database comes from COLDCHAIN_DATABASE_URL (SQLite path or postgresql+psycopg:// URL).
CMD ["python", "-m", "backend.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
