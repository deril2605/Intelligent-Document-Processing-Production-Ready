# ACU + Azure Blob Storage Workflow

This folder documents the notebook-driven storage pipeline in:

- `notebooks/02-azure-content-understanding/03-blob-storage/03-blob-storage.ipynb`

The notebook runs Azure Content Understanding (ACU) on a license agreement PDF and stores staged artifacts into Azure Blob Storage for downstream validation, analytics, and retrieval.

## Purpose

The notebook integrates:

- ACU inference (single analyzer run)
- Blob-staged artifact persistence
- Field splitting (`*_raw` and `*_normalized`)
- Retrieval-ready JSON payloads

It is designed to keep the full ACU response while also producing a slim fields-oriented artifact for DB/eval flows.

## Pipeline

```text
PDF file
  -> upload to RAW container
  -> analyze with ACU
  -> store full response in ACU container
  -> split fields (raw vs normalized)
  -> build compact fields payload
  -> store compact payload in FIELDS container
  -> retrieve and inspect payload
```

## Blob Stages and Containers

The notebook maps each stage to its own Blob container via the `Stage` enum:

- `raw`: original input file (`.pdf`)
- `acu`: full ACU response (`.json`)
- `fields`: compact, structured JSON with extracted fields (`.json`)
- `annotated`: reserved for optional annotated outputs

Container names are exactly the enum values above.

## Data Model

### Blob path

For every stage, blob name is:

- `<doc_id><ext>`

Example:

- `4f3f...-uuid.pdf` in `raw`
- `4f3f...-uuid.json` in `acu`
- `4f3f...-uuid.json` in `fields`

### JSON wrapper format

`upload_json(...)` stores a wrapper object:

```json
{
  "document_id": "<doc_id>",
  "stage": "fields",
  "timestamp": "<utc-iso-z>",
  "payload": { }
}
```

The `payload` shape depends on stage.

## Notebook Components

### 1. ACU client setup

The notebook initializes `AzureContentUnderstandingClient` using:

- `AZURE_AI_ENDPOINT`
- `AZURE_AI_API_KEY` (or Azure AD token via `DefaultAzureCredential`)
- `API_VERSION = "2025-11-01"`

### 2. Blob storage helper

`BlobStorage` is implemented as a thread-safe singleton and provides:

- container creation-once behavior
- byte/json upload and download
- stage-scoped blob listing

Key methods:

- `ensure_all_containers_ready()`
- `upload_bytes(...)`
- `upload_json(...)`
- `download_json(...)`
- `list_blobs_in_stage(...)`

### 3. Field splitting

`split_fields(raw_acu_result)` returns:

- `raw_fields`: keys ending with `_raw`
- `normalized_fields`: keys ending with `_normalized`
- `usage_summary`: token/page usage subset

Usage summary fields:

- `documentPagesStandard`
- `contextualizationTokens`
- `tokens`

## End-to-End Run Sequence (from notebook)

1. Initialize storage and ensure containers exist.
2. Create `doc_id` (`uuid4`) and set input `pdf_path`.
3. Upload PDF bytes to `Stage.RAW` as `.pdf`.
4. Run ACU analyze call:
   - `license_agreement_extraction_wrt_CUAD_v4_raw_normalized_singlepass`
5. Poll for completion.
6. Upload full ACU result to `Stage.ACU` as `.json`.
7. Split fields into raw and normalized groups.
8. Build compact payload:
   - `analyzerId`
   - `apiVersion`
   - `raw_fields`
   - `normalized_fields`
   - `usage`
9. Upload compact payload to `Stage.FIELDS` as `.json`.
10. Retrieve `Stage.FIELDS` JSON and inspect key sets.

## Prerequisites

- Azure Storage connection string in environment:
  - `AZURE_STORAGE_CONNECTION_STRING`
- ACU environment vars configured:
  - `AZURE_AI_ENDPOINT`
  - `AZURE_AI_API_KEY` (or AAD path)
- Python dependencies available in project environment:
  - `azure-storage-blob`
  - `azure-identity`
  - notebook dependencies used in `02-acu.ipynb`

## Example Retrieval Snippet

```python
storage = get_storage()
fields_doc = storage.download_json(doc_id, Stage.FIELDS, ".json")
payload = fields_doc["payload"]

print("Normalized keys:", list(payload["normalized_fields"].keys())[:5])
print("Raw keys:", list(payload["raw_fields"].keys())[:5])
print("Usage:", payload["usage"])
```

## Operational Notes

- `doc_id` is the stable correlation key across all stages.
- Full ACU response is preserved in `acu` for traceability.
- Compact `fields` artifact is intended for DB/evaluation workloads.
- `annotated` stage is available for future visual artifacts (bbox overlays, etc.).
- If environment variables are missing, initialization fails early by design.

## Input Used in Notebook

Current notebook sample uses:

- `data/AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf`

## Related Docs

- Parent ACU notebook docs:
  - `notebooks/02-azure-content-understanding/README.md`
