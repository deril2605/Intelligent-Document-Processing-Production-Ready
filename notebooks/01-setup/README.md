# Notebook 01: Setup and Connectivity Checks

Notebook file:

- `notebooks/01-setup/01-setup.ipynb`

## Purpose

Validate local environment and external dependencies before running later notebooks.

Checks covered:

- Python package availability (`psycopg2`, `redis`)
- Docker and Docker Compose availability
- PostgreSQL connectivity
- Redis connectivity
- Azure Blob connectivity
- Azure OpenAI connectivity

## Run Order

1. Run dependency checks.
2. Run Docker checks.
3. Start infrastructure (`docker compose up -d`).
4. Run Postgres + Redis tests.
5. Load `.env`.
6. Run Azure Blob and Azure OpenAI tests.

## Required Environment Variables

- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_BLOB_CONTAINER` (recommended: `documents`)
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`

## Common Issues

- `psycopg2 not installed`
  - Install project dependencies in your active virtual environment.

- Docker checks fail
  - Start Docker Desktop and rerun.

- Azure connection checks fail
  - Verify `.env` values and key validity.
