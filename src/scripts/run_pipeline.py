# scripts/run_pipeline.py
from __future__ import annotations

import argparse
import json

from src.acu.config import load_settings
from src.integration.pipeline import run_pipeline

from dotenv import load_dotenv
load_dotenv() 

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Local PDF path")
    ap.add_argument("--doc-id", default=None, help="Optional document id")
    args = ap.parse_args()

    settings = load_settings()
    out = run_pipeline(local_pdf_path=args.file, settings=settings, document_id=args.doc_id)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
