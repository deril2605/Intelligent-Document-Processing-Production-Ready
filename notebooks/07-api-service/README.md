# 07 API Service

This notebook validates and starts the FastAPI layer for the project.

File: `07-api-service.ipynb`

## What It Does
1. Starts infrastructure services (`postgres`, `redis`) using Docker Compose.
2. Shows current compose status.
3. Loads `AppConfig` and prints runtime config values.
4. Starts API process via:
   - `python run_api.py`
5. Polls health endpoint:
   - `GET /api/v1/health`
6. Prints useful URLs (`/`, `/docs`, `/api/v1/health`) and optionally opens browser.

## Prerequisites
- Run from project root:
  - `Intelligent-Document-Processing-Production-Ready`
- `run_api.py` exists at project root.
- API package exists:
  - `src/api/main.py`
- FastAPI dependencies installed in the notebook/kernel environment:
  - `fastapi`
  - `uvicorn`
- Config available (from env/.env):
  - API (`API_HOST`, `API_PORT`)
  - Postgres/Redis
  - Azure Blob + ACU values

## Notebook Flow
- Cell 1: `docker compose up -d postgres redis`
- Cell 2: `docker compose ps`
- Cell 3: prints `cfg.api`, `cfg.database`, `cfg.redis`, `cfg.azure`, `cfg.acu`
- Cell 4:
  - starts API subprocess
  - waits up to 20 attempts for health response
- Cell 5:
  - prints URLs and opens browser

## Expected Success Output
- `API healthy` during startup check
- Health endpoint returns JSON with status `healthy` or `ok`
- Docs reachable at `http://<host>:<port>/docs`

## Common Issues
- `HTTPConnectionPool ... host='0.0.0.0'`:
  - use `API_HOST=127.0.0.1` for notebook client calls.
- `run_api.py` not found:
  - ensure notebook cwd is project root or `os.chdir(...)` first.
- `ModuleNotFoundError: fastapi`:
  - install FastAPI/Uvicorn in the active kernel environment.
- Health returns `degraded`:
  - API booted but backend init failed (check env vars and service connectivity).

