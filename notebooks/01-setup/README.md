# Credit OCR System – Local Infra + Azure AI

This project is a **local-first document processing system** that uses:

- **PostgreSQL** (local, via Docker) for metadata & status
- **Redis** (local, via Docker) as a Celery broker
- **Celery** (Dockerized worker) for background processing
- **Azure Blob Storage** (cloud) for document storage
- **Azure OpenAI** (cloud) for LLM-based extraction

The system is designed so that **only infrastructure runs locally**, while **AI models and storage live in Azure**.

---

## Architecture Overview

This project follows a local-first architecture: infrastructure services (PostgreSQL, Redis, Celery) run locally (via Docker), while storage and AI inference run in Azure.

```
Local Machine (Docker)
+-----------------------------+
| Python / Notebooks / API    |  Submits jobs, uploads/downloads files
|                             |
|  PostgreSQL (Docker)        |  Stores document metadata & status
|  Redis (Docker)             |  Celery broker for background jobs
|  Celery Worker (Docker) --> |  Processes tasks and calls Azure services
+-----------------------------+

Azure Cloud
+-----------------------------+
| Azure Blob Storage          |  Document storage (blobs)
| Azure OpenAI                |  LLM-based extraction and inference
+-----------------------------+
```


Data flow (high level): local code/notebooks enqueue jobs -> Celery worker reads jobs from Redis -> worker stores/retrieves documents in Azure Blob Storage and calls Azure OpenAI for extraction -> results and status written to PostgreSQL.

---

## Prerequisites

### Required (all platforms)
- **Docker Desktop**
  - macOS: https://www.docker.com/products/docker-desktop
  - Windows: same (WSL2 enabled)
- **Python 3.11+**
- **Git**

### Recommended
- **uv** (fast Python package manager)
- **VS Code** (or any editor)

---

## Python Setup (macOS & Windows)

### 1. Install `uv`
```bash
pip install uv
```
Verify:
```bash
uv --version
```

### 2. Create virtual environment
```bash
uv venv
```
Activate:

macOS/Linux
```bash
source .venv/bin/activate
```
Windows (PowerShell)
```powershell
.venv\Scripts\activate
```

### 3. Install dependencies
```bash
uv sync
```

## Environment Variables
Create a `.env` file in the project root (do not commit this):

```env
# PostgreSQL (used by Celery inside Docker)
DATABASE_URL=postgresql+psycopg://dms:dms@postgres:5432/dms_meta

# Redis
REDIS_URL=redis://redis:6379/0

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=...
AZURE_BLOB_CONTAINER=credit-ocr

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_DEPLOYMENT=<deployment-name>
```

`.env` is automatically read by Docker Compose. For local Python / notebooks, load it manually (see below).

---

## Docker Setup (Local Infrastructure)
Services run locally:
- PostgreSQL
- Redis
- Celery Worker

Start everything:
```bash
docker compose up -d --build
```
Check status:
```bash
docker compose ps
```
Expected healthy services example:
```
postgres        healthy
redis           healthy
celery-worker   healthy
```

### Verifying Celery Worker Health
1. Check logs
```bash
docker logs -f celery-worker
```
Look for:
```
celery@celery-worker ready.
```
2. Ping the worker
```bash
docker exec -it celery-worker /bin/sh -lc \
'/opt/venv/bin/python -m celery -A credit_ocr_system.celery_app:celery_app inspect ping'
```
Expected:
```json
{
  "celery@celery-worker": {
    "ok": "pong"
  }
}
```

---

## Local Python / Notebook Usage
`.env` files are not automatically loaded by Python. Always do this first in notebooks or scripts:

```python
from dotenv import load_dotenv
load_dotenv()
```

## Infrastructure Sanity Checks

Redis
```python
import redis
redis.Redis(host="localhost", port=6379).ping()
```

Azure Blob (local machine)
```python
from azure.storage.blob import BlobServiceClient
import os

BlobServiceClient.from_connection_string(
    os.environ["AZURE_STORAGE_CONNECTION_STRING"]
)
```

Azure OpenAI (local machine)
```python
from openai import AzureOpenAI
import os

AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)
```

### Container-Level Azure Checks (Important)
Always verify from inside the Celery container:

```bash
docker exec -it celery-worker /bin/sh
```

Azure OpenAI (inside container)
```bash
/opt/venv/bin/python - <<'EOF'
from openai import AzureOpenAI
import os

client = AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)

resp = client.chat.completions.create(
    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    messages=[{"role":"user","content":"reply OK"}],
)
print(resp.choices[0].message.content)
EOF
```
Expected response: the model prints `OK` (or the configured health-check reply).

---

## Notes
- Keep secrets out of version control. Use the `.env` file and CI secrets for deployments.
- The local infra (Postgres, Redis, Celery) is intended for development only; production should run in a managed environment and point to Azure services as needed.

If you need this README exported to another location or converted to a project-level README, tell me where.
