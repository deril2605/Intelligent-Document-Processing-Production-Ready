# Notebook 03: Blob Storage Staging

Notebook file:

- `notebooks/03-blob-storage/03-blob-storage.ipynb`

## Purpose

Demonstrate staging ACU artifacts in Blob Storage after document analysis.

Flow in this notebook:

1. Run ACU analysis for a sample PDF.
2. Upload source PDF to raw stage.
3. Upload full ACU JSON output.
4. Split fields into raw/normalized sets.
5. Upload compact fields payload.
6. Retrieve and inspect staged artifacts.

## Stages in This Notebook

This notebook defines its own local `Stage` enum and uses:

- `RAW`
- `ACU`
- `FIELDS`
- `ANNOTATED`

Note: current `src/storage/storage.py` in main app uses `RAW`, `ACU`, `ANNOTATED` only. `FIELDS` here is notebook-local for experimentation.

## Required Environment Variables

- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_AI_ENDPOINT`
- `AZURE_AI_API_KEY`

## Output Pattern

For each `doc_id`, notebook stores stage artifacts and then reads back JSON to verify:

- raw artifact exists
- ACU artifact exists
- compact fields artifact exists

## Notes

- This notebook is a storage-focused prototype and not the final API contract.
- Main app now standardizes container usage under `documents` with folder prefixes (`raw/`, `acu/`, `annotated/`).
