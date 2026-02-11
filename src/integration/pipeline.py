# src/acu/pipeline.py
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional

from src.acu.analyze import analyze_document
from src.acu.config import Settings
from src.acu.parse import flatten_fields, get_fields
from src.storage.storage import Stage, get_storage


def run_pipeline(
    *,
    local_pdf_path: str,
    settings: Settings,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    End-to-end:
      1) persist RAW pdf
      2) run ACU analyzer on local file
      3) persist ACU result json
      4) return summary (doc_id + blob paths + flattened fields)
    """
    doc_id = document_id or str(uuid.uuid4())

    # Ensure env vars are present for analyze.py (it reads from os.getenv)
    # Keep your approach: pipeline just sets env once so downstream uses it.
    os.environ["AZURE_AI_ENDPOINT"] = settings.azure_ai_endpoint
    if settings.azure_ai_api_key:
        os.environ["AZURE_AI_API_KEY"] = settings.azure_ai_api_key
    os.environ["ACU_API_VERSION"] = settings.acu_api_version
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = settings.azure_storage_connection_string

    storage = get_storage()
    storage.ensure_all_containers_ready()

    # 1) store RAW
    with open(local_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    storage.upload_blob(
        doc_id,
        Stage.RAW,
        ".pdf",
        pdf_bytes,
        overwrite=True,
    )

    # 2) run ACU (local file path)
    analysis_result = analyze_document(
        analyzer_id=settings.acu_analyzer_id,
        file_path=local_pdf_path,
        endpoint=settings.azure_ai_endpoint,
        api_key=settings.azure_ai_api_key,
        api_version=settings.acu_api_version,
    )

    # 3) store ACU result
    storage.upload_document_data(
        doc_id=doc_id,
        stage=Stage.ACU,   # make sure Stage.ACU exists in your storage enum
        ext=".json",
        data=analysis_result,
        metadata={
            "analyzer_id": settings.acu_analyzer_id,
            "source_file": local_pdf_path,
            "api_version": settings.acu_api_version,
        },
        overwrite=True,
    )

    # 4) return summary (useful for UI / debugging)
    fields = get_fields(analysis_result)
    flattened = flatten_fields(fields)

    return {
        "document_id": doc_id,
        "raw_blob": f"{Stage.RAW.value}/{doc_id}.pdf",
        "acu_blob": f"{Stage.ACU.value}/{doc_id}.json",
        "extracted_fields": flattened,
    }
