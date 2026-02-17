# Intelligent Document Processing (Production Ready)

End-to-end document extraction pipeline using:

- FastAPI (`src/api`) for upload, trigger, status, and results
- Celery + Redis for async orchestration
- PostgreSQL for document/job metadata
- Azure Blob Storage for document and ACU outputs
- Azure Content Understanding (ACU) for structured extraction

## Project Structure

- `src/api`: FastAPI service, routes, response models, UI template
- `src/tasks`: Celery tasks (`process_document_async`, `run_full_pipeline_task`, `process_acu_task`)
- `src/integration`: ACU integration pipeline
- `src/dms`: document management service + storage/metadata adapters
- `src/storage`: blob stage helpers (`raw`, `acu`, `annotated`)
- `compose.yml`: Docker services (`postgres`, `redis`, `celery-worker`)
- `run_api.py`: local API entrypoint
- `start_document_pipeline.py`: optional orchestrator script

## Data Flow

1. Upload file to `/api/v1/upload`
2. File stored in `documents/raw/<document_type>/<document_id>.<ext>`
3. Trigger processing via `/api/v1/documents/{document_id}/trigger`
4. Celery runs ACU extraction
5. ACU JSON stored in `documents/acu/<document_type>/<document_id>.json`
6. Metadata/status updated in PostgreSQL
7. Results served by `/api/v1/results/{document_id}`

## Prerequisites

- Python 3.11+ (project venv recommended)
- Docker Desktop (running)
- Azure Blob Storage account and connection string
- Azure Content Understanding endpoint, API key, analyzer ID

## Environment

Create/update `.env` at project root with:

```env
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_BLOB_CONTAINER=documents

AZURE_AI_ENDPOINT=...
AZURE_AI_API_KEY=...
ACU_ANALYZER_ID=...

# Docker-side defaults
PGHOST=localhost
PGPORT=5432
PGDATABASE=dms_meta
PGUSER=dms
PGPASSWORD=dms
```

Notes:

- Do not commit `.env` or secrets.
- For local API execution (outside Docker), Redis must be `localhost`:
  - `REDIS_URL=redis://localhost:6379/0`
- Inside Docker, worker uses:
  - `REDIS_URL=redis://redis:6379/0`

## How To Run

### 1) Start infrastructure + worker

```bash
docker compose up -d
```

### 2) Activate virtual environment

```bash
# Git Bash
source .venv/Scripts/activate
```

```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1
```

### 3) Start API (local host process)

```bash
export REDIS_URL=redis://localhost:6379/0
python run_api.py
```

### 4) Open endpoints

- UI: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/api/v1/health`
- Docs: `http://127.0.0.1:8000/docs`

## UI Usage

1. Choose file (uploads only)
2. Click `Trigger` (starts processing)
3. Poll `Status` or wait for auto updates
4. View extracted fields in `Results` when completed

## Common Issues

- `Could not trigger processing for document`
  - Document may not be `text_extraction_status=ready`
  - Verify worker + Redis + DB are healthy

- Worker orange in UI but tasks run
  - Usually API process env mismatch or stale API process
  - Ensure API uses `REDIS_URL=redis://localhost:6379/0`

- `ContainerAlreadyExists` log spam
  - Benign; container-existence check is now one-time per process

- Port 8000 in use
  - Find PID: `netstat -ano | findstr :8000`
  - Kill PID: `taskkill /PID <PID> /F`

## Dataset

This project uses the **CUAD** dataset as a reference for contract clause extraction design/evaluation:

- https://www.atticusprojectai.org/cuad
