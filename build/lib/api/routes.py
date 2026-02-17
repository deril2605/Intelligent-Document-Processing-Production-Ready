from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import io
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .models import (
    DocumentResultsResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    HealthCheckResponse,
    ProcessingStatus,
)
from ..async_processing import AsyncDocumentProcessor
from ..celery_app import celery_app
from ..config import AppConfig
from ..storage.storage import Stage, get_storage

logger = logging.getLogger(__name__)
router = APIRouter()
app_config = AppConfig()


def _latest_job(extraction_jobs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not extraction_jobs:
        return None
    return extraction_jobs[0]


def _map_status(raw_status: Dict[str, Any]) -> ProcessingStatus:
    processing = str(raw_status.get("processing_status") or "").strip().lower()
    text = str(raw_status.get("text_extraction_status") or "").strip().lower()
    jobs = raw_status.get("extraction_jobs") or []
    latest = str((_latest_job(jobs) or {}).get("status") or "").strip().lower()

    if latest in {"failed", "error"} or processing == "failed":
        return ProcessingStatus.FAILED
    # Processing status is authoritative for overall completion.
    if processing == "done":
        return ProcessingStatus.COMPLETED
    if processing in {"acu running", "ocr running"} or latest in {"running", "started"}:
        return ProcessingStatus.OCR_RUNNING
    if processing in {"pending extraction", "pending"} or latest == "pending":
        return ProcessingStatus.PENDING
    if text in {"in progress", "processing"}:
        return ProcessingStatus.PROCESSING
    if text == "failed":
        return ProcessingStatus.FAILED
    if text == "completed" and processing == "done":
        return ProcessingStatus.COMPLETED
    return ProcessingStatus.PENDING


def _new_processor() -> AsyncDocumentProcessor:
    try:
        return AsyncDocumentProcessor()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processor unavailable: {exc}") from exc


def _upload_and_fetch_status(*, payload: bytes, filename: str, document_type: str) -> Dict[str, Any]:
    proc = _new_processor()
    suffix = os.path.splitext(filename)[1] or ".bin"
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(payload)
            temp_path = tmp.name

        document_id = proc.dms_service.upload_document(
            file_path=Path(temp_path),
            document_type=document_type,
            source_filename=filename,
            create_job_if_ready=False,
        )
        status = proc.get_processing_status(document_id=document_id)
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
                logger.warning("Failed to delete temporary upload file: %s", temp_path)


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form("general"),
) -> DocumentUploadResponse:
    filename = file.filename or "uploaded.bin"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _upload_and_fetch_status,
                payload=payload,
                filename=filename,
                document_type=document_type,
            ),
            timeout=120,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Upload timed out while writing to storage") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return DocumentUploadResponse(**result)


@router.post("/documents/{document_id}/trigger")
@router.post("/trigger/{document_id}")
def trigger_document_processing(document_id: str) -> Dict[str, str]:
    proc = _new_processor()
    task_id = proc.trigger_processing(document_id=document_id)
    if not task_id:
        raise HTTPException(status_code=400, detail="Could not trigger processing for document")
    return {"document_id": document_id, "task_id": task_id, "status": "queued"}


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
@router.get("/status/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(document_id: str) -> DocumentStatusResponse:
    proc = _new_processor()
    raw = proc.get_processing_status(document_id=document_id)
    if "error" in raw:
        raise HTTPException(status_code=404, detail=raw["error"])

    doc = proc.dms_service.get_document(document_id=document_id) or {}
    latest_job = _latest_job(raw.get("extraction_jobs") or [])

    return DocumentStatusResponse(
        document_id=document_id,
        status=_map_status(raw),
        text_extraction_status=raw.get("text_extraction_status"),
        processing_status=raw.get("processing_status"),
        extraction_jobs=raw.get("extraction_jobs") or [],
        acu_result_blob_path=raw.get("acu_result_blob_path"),
        filename=doc.get("source_filename"),
        upload_timestamp=doc.get("created_at"),
        error_message=(latest_job or {}).get("error_message"),
    )


def _extract_fields_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    acu_result = payload.get("acu_result", payload)
    if not isinstance(acu_result, dict):
        return {}

    def _pages_from_source(source_value: Any) -> List[int]:
        if not isinstance(source_value, str):
            return []
        pages: List[int] = []
        for chunk in source_value.split("D("):
            if not chunk:
                continue
            head = chunk.split(")", 1)[0]
            first = head.split(",", 1)[0].strip()
            try:
                page_num = int(float(first))
            except Exception:
                continue
            if page_num not in pages:
                pages.append(page_num)
        return pages

    def _coerce_field_value(field_payload: Any) -> Any:
        if not isinstance(field_payload, dict):
            return field_payload

        pages = _pages_from_source(field_payload.get("source"))

        for key in ("valueString", "valueDate", "valueNumber", "valueInteger", "valueBoolean", "valueCurrency"):
            if key in field_payload:
                return {
                    "value": field_payload[key],
                    "confidence": field_payload.get("confidence"),
                    "pages": pages,
                }

        if "valueObject" in field_payload:
            return {
                "value": field_payload["valueObject"],
                "confidence": field_payload.get("confidence"),
                "pages": pages,
            }
        if "valueArray" in field_payload:
            return {
                "value": field_payload["valueArray"],
                "confidence": field_payload.get("confidence"),
                "pages": pages,
            }

        return field_payload

    if isinstance(acu_result.get("fields"), dict):
        return {k: _coerce_field_value(v) for k, v in acu_result["fields"].items()}

    result_obj = acu_result.get("result")
    if isinstance(result_obj, dict):
        if isinstance(result_obj.get("fields"), dict):
            return {k: _coerce_field_value(v) for k, v in result_obj["fields"].items()}

        contents = result_obj.get("contents")
        if isinstance(contents, list):
            merged: Dict[str, Any] = {}
            for content in contents:
                if isinstance(content, dict) and isinstance(content.get("fields"), dict):
                    for k, v in content["fields"].items():
                        merged[k] = _coerce_field_value(v)
            if merged:
                return merged
    return {}


@router.get("/results/{document_id}", response_model=DocumentResultsResponse)
@router.get("/documents/{document_id}/results", response_model=DocumentResultsResponse)
def get_document_results(document_id: str) -> DocumentResultsResponse:
    proc = _new_processor()
    raw = proc.get_processing_status(document_id=document_id)
    if "error" in raw:
        raise HTTPException(status_code=404, detail=raw["error"])

    if str(raw.get("processing_status")).lower() != "done":
        raise HTTPException(status_code=202, detail="Document processing not yet complete")

    acu_blob_path = raw.get("acu_result_blob_path")
    if not acu_blob_path:
        raise HTTPException(status_code=404, detail="No ACU result blob path recorded for document")

    candidate_containers = [app_config.azure.storage.container_name, "documents", "credit-ocr"]
    # Preserve order while removing duplicates.
    deduped_containers = list(dict.fromkeys(candidate_containers))

    blob = None
    for container_name in deduped_containers:
        blob = proc.dms_service.storage_client.download_bytes(
            container=container_name,
            blob_name=acu_blob_path,
        )
        if blob:
            break

    if not blob:
        raise HTTPException(
            status_code=404,
            detail=f"ACU result blob not found in containers: {', '.join(deduped_containers)}",
        )

    try:
        parsed = json.loads(blob.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse ACU result JSON: {exc}") from exc

    storage = get_storage()
    has_visualization = bool(storage.download_blob(document_id, Stage.ANNOTATED, "_page_1.png"))

    return DocumentResultsResponse(
        document_id=document_id,
        status=_map_status(raw),
        acu_result_blob_path=acu_blob_path,
        acu_result=parsed,
        extracted_fields=_extract_fields_from_payload(parsed),
        has_visualization=has_visualization,
    )


@router.get("/visualization/{document_id}")
@router.get("/documents/{document_id}/visualization")
def get_document_visualization(document_id: str, page: int = 1) -> StreamingResponse:
    image = get_storage().download_blob(document_id, Stage.ANNOTATED, f"_page_{page}.png")
    if not image:
        raise HTTPException(status_code=404, detail=f"Visualization not found for document {document_id}, page {page}")
    return StreamingResponse(
        BytesIO(image),
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=visualization_{document_id}_page_{page}.png"},
    )


@router.get("/documents/{document_id}/page/{page}/image")
@router.get("/page-image/{document_id}")
def get_document_page_image(document_id: str, page: int = 1) -> StreamingResponse:
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")

    proc = _new_processor()
    pdf_data = proc.dms_service.download_document(document_id=document_id)
    if not pdf_data:
        raise HTTPException(status_code=404, detail=f"Raw document not found for {document_id}")

    try:
        pdf = fitz.open(stream=pdf_data, filetype="pdf")
        if page > len(pdf):
            raise HTTPException(status_code=404, detail=f"Page {page} out of range for document {document_id}")
        pix = pdf[page - 1].get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
        png_bytes = pix.tobytes("png")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to render page image: {exc}") from exc

    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename={document_id}_page_{page}.png"},
    )


@router.get("/documents")
def list_documents(limit: int = 50, offset: int = 0) -> List[DocumentStatusResponse]:
    proc = _new_processor()
    docs = proc.dms_service.list_documents(limit=limit, offset=offset)

    result: List[DocumentStatusResponse] = []
    for doc in docs:
        raw = proc.get_processing_status(document_id=doc["id"])
        if "error" in raw:
            continue
        latest_job = _latest_job(raw.get("extraction_jobs") or [])
        result.append(
            DocumentStatusResponse(
                document_id=doc["id"],
                status=_map_status(raw),
                text_extraction_status=raw.get("text_extraction_status"),
                processing_status=raw.get("processing_status"),
                extraction_jobs=raw.get("extraction_jobs") or [],
                acu_result_blob_path=raw.get("acu_result_blob_path"),
                filename=doc.get("source_filename"),
                upload_timestamp=doc.get("created_at"),
                error_message=(latest_job or {}).get("error_message"),
            )
        )
    return result


@router.get("/health", response_model=HealthCheckResponse)
def health_check() -> HealthCheckResponse:
    services: Dict[str, str] = {}
    overall = "healthy"

    try:
        proc = _new_processor()
        proc.dms_service.list_documents(limit=1, offset=0)
        services["database"] = "healthy"
    except Exception as exc:
        services["database"] = f"unhealthy: {exc}"
        overall = "unhealthy"

    try:
        get_storage().ensure_all_containers_ready()
        services["blob_storage"] = "healthy"
    except Exception as exc:
        services["blob_storage"] = f"unhealthy: {exc}"
        overall = "unhealthy"

    try:
        inspector = celery_app.control.inspect(timeout=4)
        ping = inspector.ping() or {}
        if ping:
            services["celery"] = "healthy"
        else:
            # Fallback: some broker/network setups may not answer ping quickly,
            # but workers still show up in stats.
            stats = inspector.stats() or {}
            if stats:
                services["celery"] = "healthy"
            else:
                services["celery"] = "degraded: no active workers"
                if overall == "healthy":
                    overall = "degraded"
    except Exception as exc:
        services["celery"] = f"degraded: {exc}"
        if overall == "healthy":
            overall = "degraded"

    return HealthCheckResponse(
        status=overall,
        timestamp=datetime.now(timezone.utc),
        services=services,
    )
