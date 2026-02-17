# Notebook 05: DMS Upload and Processing

Notebook file:

- `notebooks/05-dms-upload-and-processing/05-dms-upload.ipynb`

## Purpose

Validate the DMS layer end-to-end:

1. apply database schema
2. wire blob + postgres adapters
3. upload document through `DmsService`
4. validate metadata and download path
5. simulate status/job lifecycle transitions

## Notebook Flow

1. Connect to Postgres and run `database/schemas/schema.sql`.
2. Verify `documents` and `extraction_jobs` table columns.
3. Build `DmsService` from:
   - `AzureBlobStorageClient`
   - `PostgresMetadataRepository`
4. Upload sample PDF via `upload_document(...)`.
5. Retrieve document metadata and extraction jobs.
6. Download document bytes and verify round-trip.
7. Update extraction + processing statuses.

## Required Services/Env

- Postgres running (`dms_meta`)
- Azure Blob connection string in env
- Sample PDF in `data/`

## Notes

- Status values must match DB constraints.
- This notebook verifies repository/service behavior before async task orchestration.
