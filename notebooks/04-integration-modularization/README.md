# Integration Modularization Notebook

This folder documents the integration notebook:

- `notebooks/04-integration-modularization/04-integration.ipynb`

The notebook demonstrates how your modular `src/` packages work together in one end-to-end flow.

## Goal

Move from notebook-only experimentation to a production-style pipeline using reusable modules.

Covered modules:

- `src/acu/config.py` for typed settings loading
- `src/acu/analyze.py` for ACU analysis execution
- `src/acu/parse.py` for field extraction/flattening helpers
- `src/storage/storage.py` for staged blob persistence (`RAW`, `ACU`, `ANNOTATED`)
- `src/integration/pipeline.py` for orchestration
- `src/scripts/run_pipeline.py` for CLI execution

## Notebook Flow

## 1) Setup imports and configuration

The notebook:

- loads `.env`
- ensures repo root is importable from notebook runtime
- imports `load_settings()` from `src.acu.config`
- prints active endpoint, analyzer id, and API version

This validates that environment-driven configuration is resolved before execution.

## 2) Run integrated pipeline

The notebook calls:

- `run_pipeline(local_pdf_path=..., settings=..., document_id=...)`

Pipeline behavior:

1. Upload input PDF to blob stage `raw`
2. Run ACU analyzer against local PDF path
3. Persist full ACU response to blob stage `acu`
4. Return summary payload:
   - `document_id`
   - `raw_blob`
   - `acu_blob`
   - `extracted_fields` (flattened)

## 3) Inspect extracted fields

The notebook prints:

- total number of flattened fields
- first set of field key/value previews

This gives a quick contract-level sanity check without opening full ACU JSON.

## 4) Verify stored artifacts in Blob

The notebook downloads the ACU blob wrapper for the same `doc_id` and checks:

- wrapper keys
- metadata
- top-level ACU payload keys

This validates that orchestration and persistence are linked correctly.

## Prerequisites

- `.env` contains:
  - `AZURE_AI_ENDPOINT`
  - `AZURE_AI_API_KEY` (or token flow configured)
  - `ACU_ANALYZER_ID` (or `AZURE_AI_ANALYZER_ID`)
  - `AZURE_STORAGE_CONNECTION_STRING`
- input PDF present at:
  - `data/AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf`
- notebook executed from repo-root context (or equivalent path setup)

## Notes

- The notebook uses fixed demo `doc_id` (`integration-demo-001`). Re-running with same id overwrites staged artifacts in current storage flow.
- Module imports use `from src...`; prefer running from repository root or module mode for scripts (`python -m src.scripts.run_pipeline ...`).
- This notebook is the integration bridge between ACU extraction and storage validation, before DMS/API orchestration layers.

## Related Files

- `src/integration/pipeline.py`
- `src/acu/config.py`
- `src/acu/analyze.py`
- `src/acu/parse.py`
- `src/storage/storage.py`
- `src/scripts/run_pipeline.py`
