from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from src.async_processing import AsyncDocumentProcessor
from src.config import AppConfig

logger = logging.getLogger(__name__)

app = FastAPI(title="Intelligent Document Processing API", version="1.0.0")
cfg = AppConfig()

try:
    processor = AsyncDocumentProcessor()
    _init_error: str | None = None
except Exception as exc:
    processor = None
    _init_error = str(exc)
    logger.exception("Failed to initialize AsyncDocumentProcessor")


def _upload_and_read_status(*, payload: bytes, filename: str, document_type: str) -> Dict[str, Any]:
    # Create a fresh service instance for the request to avoid stale/shared DB connection issues.
    local_processor = AsyncDocumentProcessor()
    suffix = os.path.splitext(filename)[1] or ".bin"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(payload)
            temp_path = tmp.name

        document_id = local_processor.dms_service.upload_document(
            file_path=Path(temp_path),
            document_type=document_type,
            source_filename=filename,
        )
        status = local_processor.get_processing_status(document_id=document_id)
        return {
            "document_id": document_id,
            "source_filename": filename,
            "document_type": document_type,
            "status": status,
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                logger.warning("Failed to delete temp file: %s", temp_path)


@app.get("/api/v1/health")
def health() -> Dict[str, Any]:
    if _init_error is not None:
        return {
            "status": "degraded",
            "api_host": cfg.api.host,
            "api_port": cfg.api.port,
            "error": _init_error,
        }
    return {
        "status": "healthy",
        "api_host": cfg.api.host,
        "api_port": cfg.api.port,
    }


@app.get("/")
def root() -> Dict[str, Any]:
    return {"service": "intelligent-document-processing-api", "status": "ok"}


@app.post("/api/v1/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
) -> Dict[str, Any]:
    if processor is None:
        raise HTTPException(status_code=500, detail=f"Processor unavailable: {_init_error}")

    filename = file.filename or "uploaded.bin"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _upload_and_read_status,
                payload=payload,
                filename=filename,
                document_type=document_type,
            ),
            timeout=55,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Upload timed out while writing to storage")
    except Exception as exc:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")


@app.post("/api/v1/documents/{document_id}/trigger")
def trigger_processing(document_id: str) -> Dict[str, Any]:
    if processor is None:
        raise HTTPException(status_code=500, detail=f"Processor unavailable: {_init_error}")

    task_id = processor.trigger_processing(document_id=document_id)
    if not task_id:
        raise HTTPException(status_code=400, detail="Could not trigger processing for document")

    return {"document_id": document_id, "task_id": task_id, "status": "queued"}


@app.get("/api/v1/documents/{document_id}/status")
def get_status(document_id: str) -> Dict[str, Any]:
    if processor is None:
        raise HTTPException(status_code=500, detail=f"Processor unavailable: {_init_error}")

    status = processor.get_processing_status(document_id=document_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status
