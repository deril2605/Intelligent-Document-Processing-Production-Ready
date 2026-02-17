# Notebook 07: API Service

Notebook file:

- `notebooks/07-api-service/07-api-service.ipynb`

## Purpose

Start and validate the FastAPI layer and test upload/trigger/status/results from notebook cells.

## Notebook Flow

1. Set `REDIS_URL` for host-run API:
   - `redis://localhost:6379/0`
2. Start infra (`postgres`, `redis`) with Docker Compose.
3. Print runtime config from `AppConfig`.
4. Start API subprocess with `run_api.py`.
5. Call `/api/v1/health`.
6. Upload document to `/api/v1/upload`.
7. Trigger with `/api/v1/documents/{id}/trigger`.
8. Poll `/api/v1/documents/{id}/status`.
9. Optional SQL checks for document/job states.

## Key Endpoints Used

- `GET /api/v1/health`
- `POST /api/v1/upload`
- `POST /api/v1/documents/{document_id}/trigger`
- `GET /api/v1/documents/{document_id}/status`
- `GET /api/v1/results/{document_id}`

## Common Issues

- Connection to `0.0.0.0` fails from requests:
  - use `127.0.0.1` as client host.
- Trigger returns 400:
  - document not ready or Redis/env mismatch.
- Results 404:
  - API process is stale/old or document not completed yet.

## Notes

- API host process and Docker worker use different Redis hostnames:
  - host API: `localhost`
  - docker worker: `redis`
