# Notebook 02: Azure Content Understanding

Notebook files:

- `notebooks/02-azure-content-understanding/02-acu.ipynb`
- `notebooks/02-azure-content-understanding/02-acu-better.ipynb`

Supporting helpers:

- `content_understanding_client.py`
- `sample_helper.py`

## Purpose

Build and test ACU analyzers for license agreements with CUAD-aligned fields.

The notebooks iterate through analyzer designs, then move to a cleaner single-pass flow for:

- `*_raw` fields for grounding and source spans
- `*_normalized` fields for structured downstream use

## What 02-acu.ipynb Covers

1. Baseline analyzer creation and analysis.
2. Save ACU responses to JSON for inspection.
3. Compare analyzer strategies:
   - combined raw + normalized
   - split raw-only and normalized-only analyzers
4. Performance and token/cost comparison.
5. Final optimized analyzer variants (including no-OCR option).

## What 02-acu-better.ipynb Covers

1. Utility functions for analysis + JSON persistence.
2. Analyzer creation for the final single-pass schema.
3. Document analysis execution.
4. Visualization of raw-field sources on PDF pages.
5. Printing normalized fields in table form.

## Required Environment Variables

- `AZURE_AI_ENDPOINT`
- `AZURE_AI_API_KEY`
- `AZURE_AI_API_VERSION` (if applicable in your helper)
- `ACU_GPT41_MINI_DEPLOYMENT` (for new Azure accounts when setting ACU defaults)

Analyzer provisioning for the app now uses:

- `ops/analyzers/license_agreement/create_license_agreement_analyzer.py`

## Input Used

- `data/AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf`

## Notes

- Keep analyzer IDs stable once finalized; update only when schema changes.
- ACU result shape used later by API/results is under `acu_result.result.contents[].fields`.
- If visualization fails on Windows, ensure Poppler is installed and configured for `pdf2image`.
