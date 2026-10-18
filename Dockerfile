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
COPY data/ data/

# Copy static frontend build from Stage 1 into FastAPI mount directory
COPY --from=frontend-builder /app/frontend/out ./frontend/out

# Configuration & Defaults
ENV PYTHONUNBUFFERED=1
ENV COLDCHAIN_DB=data/coldchain.db
ENV COLDCHAIN_CONFIG=config/customers.json
ENV COLDCHAIN_DEMO_PASSWORD=nimbus123

EXPOSE 8000

# Docker Healthcheck
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start Coldline Demo Service (Replays baseline telemetry, provisions tenants, serves dashboard & AI APIs)
CMD ["python", "-m", "backend.cli", "demo", "--db", "data/coldchain.db", "--assume-utc", "--port", "8000"]
