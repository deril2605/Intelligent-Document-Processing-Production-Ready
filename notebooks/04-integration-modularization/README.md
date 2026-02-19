# Notebook 04: Integration Modularization

Notebook file:

- `notebooks/04-integration-modularization/04-integration.ipynb`

## Purpose

Run a modular end-to-end integration using `src/` packages instead of notebook-only code.

## Covered Modules

- `src/acu/config.py`
- `src/acu/analyze.py`
- `src/acu/parse.py`
- `src/integration/pipeline.py`
- `src/storage/storage.py`

## Notebook Flow

1. Load settings and print active config values.
2. Run integrated pipeline for a sample PDF and fixed `document_id`.
3. Inspect extracted fields returned by pipeline result.
4. Download and inspect ACU artifact from blob storage.

## Prerequisites

- `.env` configured with Azure Storage + ACU credentials.
- Sample PDF available in `data/`.
- Run from repo root so `src` imports resolve.

## Notes

- Reusing a fixed demo `document_id` may overwrite previous artifacts.
- This notebook is the bridge from ACU experiments to reusable production modules.
- Analyzer resolution in runtime currently prefers hardcoded `document_type -> analyzer_id` mapping in `src/config/system.py`.
