# Notebook 06: Async Processing

Notebook file:

- `notebooks/06-async-processing/06-async-processing.ipynb`

## Purpose

Validate asynchronous processing with Celery using your DMS + ACU pipeline.

## Notebook Flow

1. Build Postgres and Blob adapters.
2. Initialize `DmsService`.
3. Upload a sample PDF.
4. Trigger background processing via `AsyncDocumentProcessor`.
5. Poll status repeatedly until completion/failure.

Polled values include:

- `text_extraction_status`
- `processing_status`
- latest extraction job status/error

## Prerequisites

- Docker services running:
  - `postgres`
  - `redis`
  - `celery-worker`
- Valid Azure env vars for Blob + ACU
- For fresh Azure accounts, ensure ACU defaults are initialized (`ACU_GPT41_MINI_DEPLOYMENT` is set before analyzer creation).
- Sample PDF exists in `data/`

## Expected Success

- `processing_status` transitions to `done`
- latest extraction job status becomes `done`
- `acu_result_blob_path` is populated
- trace chain is visible in Application Insights for Celery tasks

## Common Issues

- Stuck at pending/running:
  - worker not healthy
  - Redis host mismatch
  - ACU credentials/analyzer misconfigured
- `ContainerAlreadyExists` logs:
  - benign; container already exists

- Celery tasks run but no traces in Azure:
  - ensure `APPLICATIONINSIGHTS_CONNECTION_STRING` is available to the worker environment
  - restart worker after env changes
