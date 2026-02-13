# DMS Upload and Processing Notebook

This folder documents the workflow in:

- `notebooks/05-dms-upload-and-processing/05-dms-upload.ipynb`

The notebook validates the end-to-end DMS path:

1. Ensure PostgreSQL schema
2. Initialize Blob + Postgres adapters
3. Upload a PDF through `DmsService`
4. Verify metadata and blob retrieval
5. Simulate processing lifecycle and extraction job updates

## What This Notebook Covers

## 1) Database Setup

The notebook connects to local Postgres (`dms_meta`) using `psycopg2` and applies:

- `database/schemas/schema.sql`

It then checks table columns for:

- `documents`
- `extraction_jobs`

This confirms schema compatibility before service usage.

## 2) Adapter Wiring

It composes service dependencies with:

- `AzureBlobStorageClient` (`src/dms/adapters.py`)
- `PostgresMetadataRepository` (`src/dms/adapters.py`)
- `DmsService` (`src/dms/service.py`)

Blob client is created from:

- `AZURE_STORAGE_CONNECTION_STRING`

and uses container:

- `documents`

## 3) Upload Flow

The notebook uploads:

- `data/AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf`

via:

- `dms_service.upload_document(...)`

Upload behavior:

- Stores PDF bytes in Azure Blob under a generated path like `raw/<document_type>/<uuid>.pdf`
- Inserts a metadata row into `documents`
- Creates an extraction job when the file is extraction-ready

After upload it fetches:

- document metadata (`get_document`)
- extraction jobs (`get_extraction_jobs`)

## 4) Download + Metadata Validation

The notebook verifies:

- binary round-trip with `download_document(...)`
- direct DB inspection (`SELECT * FROM documents ORDER BY created_at DESC`)

This checks that blob persistence and metadata persistence are linked correctly.

## 5) Processing Lifecycle Simulation

The notebook simulates processing transitions:

- `text_extraction_status: ready -> completed`
- `processing_status: pending extraction -> acu running -> done`
- extraction job status update to `done`

Methods used:

- `update_textextraction_status(...)`
- `mark_acu_running(...)`
- `mark_processing_done(...)`
- `update_extraction_job(...)`

It then prints final document and job status.

## Prerequisites

- Local Postgres available on:
  - host: `localhost`
  - port: `5432`
  - db: `dms_meta`
  - user/password: `dms` / `dms`
- Azure Blob connection string set in environment:
  - `AZURE_STORAGE_CONNECTION_STRING`
- Python dependencies installed (`psycopg2`, `azure-storage-blob`, etc.)

## Notes

- The notebook uses `Path.cwd()` and expects repo-root execution context so relative paths (like `database/schemas/schema.sql` and `data/...pdf`) resolve correctly.
- Status values must stay aligned with `database/schemas/schema.sql` check constraints.
- This notebook is integration-focused (schema + service + adapters), not just unit-level validation.

## Related Source Files

- `src/dms/service.py`
- `src/dms/adapters.py`
- `src/dms/interfaces.py`
- `database/schemas/schema.sql`
