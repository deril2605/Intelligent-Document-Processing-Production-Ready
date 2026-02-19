# Notebook 09: App Setup

Notebook file:

- `notebooks/09-app-setup/09-app-setup.ipynb`

## Purpose

Quick-start the local app stack from notebook cells:

- Docker infra (`postgres`, `redis`)
- Celery worker (host process)
- FastAPI service (host process)
- Health checks and URL launch

## Notebook Flow

1. Start infra: `docker compose up -d postgres redis`
2. Show `docker compose ps`
3. Print active `AppConfig`
4. Start Celery worker process
5. Start API process via `run_api.py`
6. Poll `/api/v1/health` until ready
7. Print/open UI and docs URLs
8. Verify traces in Application Insights (API + Celery)

## Prerequisites

- Docker Desktop running
- Python venv active with project dependencies
- `.env` configured
- `.env` includes `APPLICATIONINSIGHTS_CONNECTION_STRING` for telemetry export

Recommended for host API in notebook session:

- `REDIS_URL=redis://localhost:6379/0`

## Troubleshooting

- `WinError 10048` (port in use)
  - stop existing API process on `:8000`
- `0.0.0.0` request failures
  - call `127.0.0.1` from notebook/client
- Celery worker permission/pool issues on Windows host
  - prefer Docker worker for stability
- No telemetry appears in Azure
  - restart API and Celery after setting OTel env vars
  - verify `/api/v1/health` trace appears first in Application Insights
