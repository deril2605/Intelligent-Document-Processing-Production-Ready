# Docling Provider POC

Notebook:

- `notebooks/08-docling-provider-poc/08-docling-provider-poc.ipynb`

This POC validates whether Docling can be used as an alternative extraction backend (adapter) to ACU.

It checks:

- structured field extraction via Docling templates
- provenance/bounding box availability from Docling document JSON
- shaping output into a provider-agnostic, ACU-like field contract

## Run notes

- Execute from repository root so `data/...pdf` resolves.
- If needed, install Docling first:
  - `pip install "docling[vlm]"`

## Expected outcome

You should be able to confirm whether field extraction quality and field-to-bbox mapping are sufficient for introducing a `src/docling/` adapter behind your common extraction interface.
