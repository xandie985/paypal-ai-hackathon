# One image, one web service: the API serves the built frontend, so a judge opens a single URL.
# Build:  docker build -t pactguard .      Run:  docker run -p 8000:8000 --env-file .env pactguard

FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# The AG Studio licence key is public by design: it ships in the browser bundle. Render passes service
# environment variables to the build as build args. Never put a PayPal or LLM key in a VITE_ variable.
ARG VITE_AG_STUDIO_LICENSE=""
ENV VITE_AG_STUDIO_LICENSE=$VITE_AG_STUDIO_LICENSE
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=frontend /build/frontend/dist frontend/dist
# The filesystem is ephemeral on Render: the ledger resets on restart and the seeded history is rebuilt on demand.
ENV FRONTEND_DIST=/app/frontend/dist LEDGER_PATH=/tmp/ledger.db
WORKDIR /app/backend
# ONE worker: run sessions live in process memory (app/runs.py), so a second worker would 404 on runs it never saw.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
