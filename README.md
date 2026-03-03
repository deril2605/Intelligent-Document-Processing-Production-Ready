# Intelligent Document Processing (Production Ready)

End-to-end document extraction pipeline using:

- FastAPI (`src/api`) for upload, trigger, status, and results
- Celery + Redis for async orchestration
- PostgreSQL for document/job metadata
- Azure Blob Storage for document and ACU outputs
- Azure Content Understanding (ACU) for structured extraction

## Architecture
![alt text](images/archi.png)

## Data Flow
![alt text](images/data-flow.png)

## Project Structure

- `src/api`: FastAPI service, routes, response models, UI template
- `src/tasks`: Celery tasks (`process_document_async`, `run_full_pipeline_task`, `process_acu_task`)
- `src/integration`: ACU integration pipeline
- `src/dms`: document management service + storage/metadata adapters
- `src/storage`: blob stage helpers (`raw`, `acu`, `annotated`)
- `compose.yml`: Docker services (`postgres`, `redis`, `celery-worker`)
- `run_api.py`: local API entrypoint
- `start_document_pipeline.py`: optional orchestrator script
- `ops/`: analyzer scripts + database SQL assets for repeatable rollout

## UI Screenshots

#### Home Page
![alt text](images/home-ui.png)

#### Visual UI
![alt text](images/visual-ui.png)

#### Norm fields UI
![alt text](images/norm-fields.png)

## Data Flow

1. Upload file to `/api/v1/upload`
2. API auto-runs ACU classifier and stores detected `document_type`
3. File stored in `documents/raw/<document_type>/<document_id>.<ext>`
4. User can override detected type, then trigger via `/api/v1/documents/{document_id}/trigger`
5. Celery runs ACU extraction with analyzer mapped to final `document_type`
6. ACU JSON stored in `documents/acu/<document_type>/<document_id>.json`
7. Metadata/status updated in PostgreSQL
8. Results served by `/api/v1/results/{document_id}`

## Structured Data Persistence (Postgres)

This project persists structured data in two layers:

1. Operational metadata tables (always used)
2. Reviewed document-type tables (optional, enabled via `ops/db/reviewed_tables`)

### Operational metadata (always on)

Core tables in `dms_meta` track ingestion and pipeline execution:

- `documents`
  - document identity and file metadata
  - blob pointers (`blob_path`, `acu_result_blob_path`)
  - extraction + processing status fields
  - audit timestamps (`created_at`, `updated_at`)
- `extraction_jobs`
  - async job lifecycle and error state per document
  - creation/completion timestamps

Write path in code:

- Upload/register: `src/dms/service.py`
- DB adapter: `src/dms/adapters.py`
- Async updates: `src/tasks/pipeline_tasks.py`

### Reviewed structured outputs (optional)

For typed business-ready outputs (for example license-agreement normalized fields), apply SQL assets from:

- `ops/db/reviewed_tables/`
- `ops/db/migrations/`

These tables are intended for downstream app/reporting workflows, while full ACU payloads remain in Blob for traceability.

### Blob vs DB responsibility

- Azure Blob stores large artifacts:
  - source files (`documents/raw/...`)
  - full ACU JSON (`documents/acu/...`)
- Postgres stores queryable structured state and relationships:
  - statuses, job progression, document typing, reviewed normalized rows


### Database Tables

![alt text](images/tables.png)

#### Documents Table
![alt text](images/doc_table.png)

#### License Agreement Table
![alt text](images/lic_agg_table.png)

#### Service Agreement Table
![alt text](images/serv_agg_table.png)

## Prerequisites

- Python 3.11+ (project venv recommended)
- Docker Desktop (running)
- Azure Blob Storage account and connection string
- Azure Content Understanding endpoint, API key

## Environment

Create/update `.env` at project root with:

```env
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_BLOB_CONTAINER=documents

AZURE_AI_ENDPOINT=...
AZURE_AI_API_KEY=...
AZURE_AI_API_VERSION=2025-11-01
# Required when setting ACU defaults for a fresh Azure account:
ACU_GPT41_MINI_DEPLOYMENT=...

# Observability (OpenTelemetry -> Azure Application Insights)
APPLICATIONINSIGHTS_CONNECTION_STRING=...
OTEL_SERVICE_NAME=intelligent-document-processing-api
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=dev,service.namespace=idp
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=1.0

# Docker-side defaults
PGHOST=localhost
PGPORT=5432
PGDATABASE=dms_meta
PGUSER=dms
PGPASSWORD=dms
REDIS_URL=redis://localhost:6379/0
```

Notes:

- Do not commit `.env` or secrets.
- Local host processes (API/notebooks) require:
  - `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `REDIS_URL`
- Inside Docker, `compose.yml` explicitly overrides service connectivity for worker:
  - `PGHOST=postgres`
  - `REDIS_URL=redis://redis:6379/0`

## Ops Bootstrap (Run Before Starting Project)

Run these once per new Azure account/subscription (or whenever you need to recreate ACU assets).

### 1) Activate venv and run from project root

```bash
# Git Bash
source .venv/Scripts/activate
```

```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1
```

### 2) Create ACU analyzers/classifier

Recommended order:

1. License analyzer (also handles `gpt-4.1-mini` defaults if missing)
2. Service analyzer
3. CUAD classifier

```bash
python -m ops.analyzers.license_agreement.create_license_agreement_analyzer
python -m ops.analyzers.service_agreement.create_service_agreement_analyzer
python -m ops.classifier.create_cuad_classifier
```

If you get `DefaultsNotSet` or model deployment errors, set:

```env
ACU_GPT41_MINI_DEPLOYMENT=<your-azure-openai-deployment-name>
```

then rerun step 2.

### 3) (Optional) Apply DB SQL assets for reviewed output tables

SQL files are in:

- `ops/db/migrations/`
- `ops/db/reviewed_tables/`

Run them in your SQL client (for example DBeaver) against `dms_meta` before using full review/write flows.

## How To Run

### 1) Start infrastructure + worker

```bash
docker compose up -d --build
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

## Restart (Docker + Host API)

```bash
docker compose down
docker compose up -d --build
```

Then restart host API process:

```bash
python run_api.py
```

## Observability

OTel instrumentation is wired in:

- API startup (`src/api/main.py`)
- Celery worker startup (`src/celery_app.py`)
- Async queue propagation (`src/async_processing.py`)
- Celery task spans (`src/tasks/pipeline_tasks.py`)
- ACU integration spans (`src/integration/pipeline.py`)

### Verify in Azure

1. Open Application Insights -> `Search` (View as `Traces`).
2. Trigger one end-to-end run (upload -> trigger -> status -> results).
3. Confirm trace entries such as:
   - `GET /api/v1/health`
   - `process_document_async`
   - `run_full_pipeline_task`
   - `process_acu_task`
   - `process_document_with_acu`

Sample KQL:

```kusto
requests
| where timestamp > ago(30m)
| project timestamp, name, resultCode, duration, operation_Id, cloud_RoleName
| order by timestamp desc
```

## Analyzer and Table Ops

Use the dedicated `ops/` folder for per-document-type rollout:

- Analyzer scripts:
  - `ops/analyzers/license_agreement/create_license_agreement_analyzer.py`
  - `ops/analyzers/license_agreement/schema.json`
- SQL assets:
  - `ops/db/reviewed_tables/reviewed_license_agreement.sql`
  - `ops/db/migrations/`

Create analyzers/classifier:

```bash
python -m ops.analyzers.license_agreement.create_license_agreement_analyzer
python -m ops.analyzers.service_agreement.create_service_agreement_analyzer
python -m ops.classifier.create_cuad_classifier
```

Analyzers
![alt text](images/analyzers.png)

Apply reviewed table SQL (example):

```sql
-- Run the contents of this file in DBeaver SQL editor:
-- ops/db/reviewed_tables/reviewed_license_agreement.sql
```

### Analyzer Resolution (Current)

ACU analyzer selection is resolved at runtime from a hardcoded map keyed by `document_type` in:

- `src/config/system.py`

Lookup order:

1. `HARDCODED_ACU_ANALYZERS[document_type]`
2. Default hardcoded fallback (`license-agreement`) if needed

Analyzer/classifier IDs are code-owned and do not require `compose.yml` env entries.

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

- No traces in Application Insights
  - Ensure `APPLICATIONINSIGHTS_CONNECTION_STRING` is set in environment where API/worker run.
  - Restart both API and worker after env changes.
  - Verify requests appear first (`/api/v1/health`) before checking task spans.

- `ContainerAlreadyExists` log spam
  - Benign; container-existence check is now one-time per process

- Port 8000 in use
  - Find PID: `netstat -ano | findstr :8000`
  - Kill PID: `taskkill /PID <PID> /F`

## Dataset

This project uses the **CUAD** dataset as a reference for contract clause extraction design/evaluation:

- https://www.atticusprojectai.org/cuad
