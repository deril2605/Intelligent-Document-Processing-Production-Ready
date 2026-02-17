# 06 Async Processing

This notebook demonstrates end-to-end asynchronous document processing using:
- Azure Blob Storage
- Postgres metadata DB
- Celery background worker
- ACU processing pipeline

File: `06-async-processing.ipynb`

## What It Does
1. Connects to Postgres (`dms_meta`).
2. Builds `DmsService` with Azure Blob + Postgres adapters.
3. Uploads a sample PDF and creates document metadata.
4. Triggers async processing with `AsyncDocumentProcessor`.
5. Polls status until processing is `done` or `failed`.

## Prerequisites
- Docker services running:
  - `postgres`
  - `redis`
  - `celery-worker`
- Environment configured (at minimum):
  - `AZURE_STORAGE_CONNECTION_STRING`
  - Postgres credentials (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`) if you override defaults
- Sample PDF present at:
  - `data/AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf`

## Notebook Flow
- Create DB connection.
- Resolve current working directory.
- Initialize DMS + async processor.
- Upload document with `document_type="license-agreement"`.
- Trigger:
  - `async_processor.trigger_processing(document_id=...)`
- Monitor loop (20 checks, 7s interval):
  - `text_extraction_status`
  - `processing_status`
  - latest extraction job status/error

## Expected Success Output
- `Processing status: done`
- latest job status becomes `done`
- document has `acu_result_blob_path` populated in metadata

## Common Issues
- Stuck in pending:
  - Celery worker not running or wrong Celery app target.
- ACU connection errors:
  - Missing/wrong `AZURE_AI_ENDPOINT`, `AZURE_AI_API_KEY`, `ACU_ANALYZER_ID`.
- Blob container mismatch:
  - Ensure `AZURE_BLOB_CONTAINER=documents` if using the current architecture.

