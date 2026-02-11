# License Agreement Extraction with Azure Content Understanding (CUAD)

## Overview

This notebook package implements a production-oriented extraction pipeline for License Agreements using Azure Content Understanding (ACU).

The pipeline extracts two complementary outputs in one analyzer run:

- Raw text spans for grounding and bounding box visualization.
- Normalized structured fields for validation, analytics, and database ingestion.

The schema is aligned to the CUAD-style legal extraction requirements and optimized for:

- Legal clause grounding
- Bounding box visualization
- Structured validation
- Cost efficiency
- Performance stability

Notebook reference: `notebooks/02-azure-content-understanding/02-acu.ipynb`

## Architecture

```text
Input PDF (License Agreement)
        |
        v
Azure Content Understanding
        |
        v
Single Combined Analyzer
   |- *_raw fields (anchored, bbox-ready)
   |- *_normalized fields (machine-friendly)
        |
        v
Visualization Engine (Matplotlib)
        |
        v
Structured JSON Output (for DB validation)
```

## What Is Implemented

### 1. Single Combined Custom Analyzer

A combined analyzer is used to extract both grounding-oriented and normalized fields in a single pass.

#### Raw fields (bounding box ready)

- `DocumentName_raw`
- `Parties_raw`
- `AgreementDate_raw`
- `EffectiveDate_raw`
- `ExpirationDate_raw`
- `RenewalTerm_raw`
- `NoticeToTerminateRenewal_raw`
- `GoverningLaw_raw`
- `LicenseGrant_raw`
- `Exclusivity_raw`
- `TerminationForConvenience_raw`

Raw field characteristics:

- Preserves original document phrasing
- Retains span anchoring
- Produces `source: D(page,x1,y1,...)`
- Enables precise per-clause bounding box drawing

#### Normalized fields (structured storage)

- `DocumentName_normalized`
- `Parties_normalized`
- `AgreementDate_normalized`
- `AgreementDateISO`
- `EffectiveDateISO`
- `ExpirationDateISO`
- `Renewal_normalized`
- `Notice_normalized`
- `Exclusivity_normalized`
- `TerminationForConvenience_normalized`

Normalized field characteristics:

- Standardized ISO date outputs
- Structured clause representation
- Normalized boolean/Yes-No logic
- Ready for relational/document DB ingestion

## Analyzer Configuration

Final production configuration:

```json
{
  "config": {
    "returnDetails": false,
    "enableOcr": false,
    "enableLayout": true,
    "estimateFieldSourceAndConfidence": true
  }
}
```

Rationale:

- `returnDetails: false` reduces payload size and latency.
- `enableOcr: false` is appropriate for digital SEC-style PDFs where OCR is unnecessary.
- `enableLayout: true` is required for reliable source geometry.
- `estimateFieldSourceAndConfidence: true` is required for source quads and confidence metrics.

## Bounding Box Visualization

The notebook visualization workflow includes:

- Parsing multiple `D(...)` source quads per field.
- Handling span-level and multi-line sources.
- Converting ACU page coordinates to rendered image pixels.
- Confidence-based color coding:
  - Green: `>= 90%`
  - Yellow: `70-89%`
  - Red: `< 70%`

This supports visual validation of extracted clauses directly over page images.

## Token and Cost Analysis

Observed runs:

| Setup | Input Tokens | Output Tokens | Total |
|---|---:|---:|---:|
| Normalized Only | 9,572 | 226 | 9,798 |
| Raw Only | 12,176 | 965 | 13,141 |
| Combined | 16,119 | 1,877 | 17,996 |
| Final Optimized | 16,314 | 1,961 | 18,275 |

Estimated model cost (`gpt-4.1-mini`) for a 10-page document:

- Approximately `$0.01` per document.

This is cost-efficient for full clause extraction plus grounding and normalization.

## Performance Observations

Observed timings:

- Initial analyzer: around `23s`
- Combined raw + normalized analyzer: around `75s`

Primary contributors:

- Field grounding (`estimateFieldSourceAndConfidence`)
- Layout mapping
- Multi-span raw clause extraction
- Long legal clause text spans

OCR was not a major contributor for digitally generated PDFs.

## Design Decision: One Combined Analyzer

One combined analyzer is preferred for this CUAD-oriented workflow.

Benefits:

- Single document pass
- Single contextualization cost
- Cleaner orchestration
- Lower total run cost versus two independent full runs

Two separate analyzers are mainly useful when:

- Raw grounding is very heavy and optional
- Raw extraction is conditionally triggered

For this use case, a combined analyzer is the default approach.

## Example Document Used

Tested on:

- `data/AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf`

Observed outcome:

- 10 pages processed
- Accurate clause grounding
- ISO date normalization
- Renewal term parsing
- Notice period parsing
- Exclusive/non-exclusive detection

## Poppler Setup (Windows)

`pdf2image` requires Poppler on Windows to render PDF pages for visualization.

Install steps:

1. Download latest release from:
   `https://github.com/oschwartz10612/poppler-windows/releases`
2. Extract to a local folder, for example:
   `C:\Users\deril\poppler`
3. Use Poppler `bin` path in notebook code:

```python
from pdf2image import convert_from_path

pdf_images = convert_from_path(
    "data/AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf",
    poppler_path=r"C:\Users\deril\poppler\Library\bin",
)
```

You can alternatively add the Poppler `bin` folder to system PATH to avoid passing `poppler_path` each time.

## Notes

- Keep credentials in `.env` and never commit secrets.
- ACU output sources can contain multiple `D(...)` entries separated by `;`. Visualization code must parse all quads, not just the first.
- If bounding boxes appear incomplete, verify that multi-quad parsing is enabled and that `enableLayout` plus `estimateFieldSourceAndConfidence` are both enabled in analyzer config.
