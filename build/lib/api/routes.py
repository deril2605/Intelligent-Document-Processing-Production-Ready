from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import io
import threading
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz
import psycopg2
import redis
from psycopg2 import sql
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from opentelemetry import trace

from .models import (
    DocumentResultsResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    HealthCheckResponse,
    ProcessingStatus,
    SaveReviewRequest,
    SaveReviewResponse,
)
from ..async_processing import AsyncDocumentProcessor
from ..celery_app import celery_app
from ..config import AppConfig
from ..storage.storage import Stage, get_storage
from ..visualization import build_acu_annotated_pages

logger = logging.getLogger(__name__)
router = APIRouter()
app_config = AppConfig()
tracer = trace.get_tracer(__name__)
_FIELD_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


def _set_span_attrs(attributes: Dict[str, Any]) -> None:
    span = trace.get_current_span()
    if span is None:
        return
    for key, value in attributes.items():
        if value is None:
            continue
        span.set_attribute(key, value)


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


def _sanitize_table_suffix(document_type: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", document_type.strip().lower()).strip("_")
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid document_type")
    if len(normalized) > 48:
        normalized = normalized[:48]
    return normalized


def _validate_normalized_fields(normalized_fields: Dict[str, str]) -> Dict[str, str]:
    if not isinstance(normalized_fields, dict) or not normalized_fields:
        raise HTTPException(status_code=400, detail="normalized_fields must be a non-empty object")

    cleaned: Dict[str, str] = {}
    for key, value in normalized_fields.items():
        if not isinstance(key, str) or not _FIELD_KEY_PATTERN.match(key):
            raise HTTPException(status_code=400, detail=f"Invalid field key: {key!r}")

        if value is None:
            cleaned[key] = ""
            continue

        if not isinstance(value, str):
            value = str(value)

        value = value.strip()
        if len(value) > 10000:
            raise HTTPException(status_code=400, detail=f"Value too long for field: {key}")
        cleaned[key] = value

    return cleaned


def _db_column_from_field_key(field_key: str) -> str:
    # Store reviewed normalized values without the technical suffix.
    if field_key.lower().endswith("_normalized"):
        base = field_key[: -len("_normalized")]
    else:
        base = field_key

    base = base.strip("_")
    if not base or not _FIELD_KEY_PATTERN.match(base):
        raise HTTPException(status_code=400, detail=f"Invalid DB column derived from field key: {field_key!r}")
    return base


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
    _set_span_attrs({"idp.operation": "upload_document", "idp.document_type": document_type})
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
def trigger_document_processing(
    document_id: str,
    reuse_existing: bool = Query(
        False,
        description="If true, reuse existing ACU blob/result and skip a new ACU run.",
    ),
) -> Dict[str, str]:
    _set_span_attrs(
        {
            "idp.operation": "trigger_document_processing",
            "idp.document_id": document_id,
            "idp.reuse_existing": reuse_existing,
        }
    )
    proc = _new_processor()

    if reuse_existing:
        doc = proc.dms_service.get_document(document_id=document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        existing_blob = doc.get("acu_result_blob_path")
        if not existing_blob:
            raise HTTPException(
                status_code=400,
                detail="No existing ACU result found for this document; cannot reuse.",
            )

        # Keep DB status consistent so UI polling resolves to completed.
        try:
            proc.dms_service.update_textextraction_status(document_id=document_id, status="completed")
        except Exception:
            logger.warning("Could not set text_extraction_status=completed for %s", document_id)
        try:
            proc.dms_service.mark_processing_done(document_id=document_id)
        except Exception:
            logger.warning("Could not set processing_status=done for %s", document_id)

        # Best effort: generate annotated overlays from existing ACU blob so UI can show bounding boxes
        # without running a new ACU extraction.
        try:
            candidate_containers = [app_config.azure.storage.container_name, "documents", "credit-ocr"]
            deduped_containers = list(dict.fromkeys(candidate_containers))
            acu_blob_bytes = None
            for container_name in deduped_containers:
                acu_blob_bytes = proc.dms_service.storage_client.download_bytes(
                    container=container_name,
                    blob_name=existing_blob,
                )
                if acu_blob_bytes:
                    break

            pdf_data = proc.dms_service.download_document(document_id=document_id)
            if acu_blob_bytes and pdf_data:
                parsed = json.loads(acu_blob_bytes.decode("utf-8"))
                acu_result = parsed.get("acu_result", parsed)
                annotated_pages = build_acu_annotated_pages(pdf_data=pdf_data, acu_result=acu_result)
                for page_num, image_bytes in annotated_pages.items():
                    proc.dms_service.storage_client.upload_bytes(
                        container="documents",
                        blob_name=f"annotated/{document_id}_page_{page_num}.png",
                        data=image_bytes,
                        content_type="image/png",
                    )
        except Exception as exc:
            logger.warning("Reuse mode overlay generation failed for %s: %s", document_id, exc)

        return {
            "document_id": document_id,
            "task_id": "existing-data",
            "status": "reused",
        }

    task_id = proc.trigger_processing(document_id=document_id)
    if not task_id:
        raise HTTPException(status_code=400, detail="Could not trigger processing for document")
    return {"document_id": document_id, "task_id": task_id, "status": "queued"}


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
@router.get("/status/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(document_id: str) -> DocumentStatusResponse:
    _set_span_attrs({"idp.operation": "get_document_status", "idp.document_id": document_id})
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
    _set_span_attrs({"idp.operation": "get_document_results", "idp.document_id": document_id})
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
    total_pages: Optional[int] = None
    try:
        pdf_bytes = proc.dms_service.download_document(document_id=document_id)
        if pdf_bytes:
            pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(pdf)
            pdf.close()
    except Exception:
        total_pages = None

    return DocumentResultsResponse(
        document_id=document_id,
        status=_map_status(raw),
        acu_result_blob_path=acu_blob_path,
        acu_result=parsed,
        extracted_fields=_extract_fields_from_payload(parsed),
        has_visualization=has_visualization,
        total_pages=total_pages,
    )


@router.post("/documents/{document_id}/review", response_model=SaveReviewResponse)
def save_reviewed_normalized_fields(
    document_id: str,
    payload: SaveReviewRequest,
) -> SaveReviewResponse:
    _set_span_attrs(
        {
            "idp.operation": "save_reviewed_normalized_fields",
            "idp.document_id": document_id,
            "idp.document_type": payload.document_type,
        }
    )

    proc = _new_processor()
    doc = proc.dms_service.get_document(document_id=document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if str(doc.get("processing_status", "")).lower() != "done":
        raise HTTPException(status_code=409, detail="Document must be completed before saving reviewed fields")

    selected_document_type = payload.document_type.strip()
    if not selected_document_type:
        raise HTTPException(status_code=400, detail="document_type is required")

    actual_document_type = str(doc.get("document_type") or "").strip()
    if actual_document_type and selected_document_type.lower() != actual_document_type.lower():
        raise HTTPException(
            status_code=400,
            detail=(
                f"document_type mismatch. Selected '{selected_document_type}' "
                f"but document is '{actual_document_type}'"
            ),
        )

    normalized_fields = _validate_normalized_fields(payload.normalized_fields)
    table_name = f"reviewed_{_sanitize_table_suffix(selected_document_type)}"

    cfg = AppConfig()
    conn = None
    try:
        conn = psycopg2.connect(**cfg.database.psycopg2_dsn)
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        document_type VARCHAR(100) NOT NULL,
                        source_filename VARCHAR(255),
                        source VARCHAR(30) NOT NULL DEFAULT 'ui-review',
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                    )
                    """
                ).format(sql.Identifier(table_name))
            )
            cursor.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (document_id)").format(
                    sql.Identifier(f"{table_name}_document_id_idx"),
                    sql.Identifier(table_name),
                )
            )

            db_field_map: Dict[str, str] = {}
            for field_key, field_value in normalized_fields.items():
                db_col = _db_column_from_field_key(field_key)
                if db_col in db_field_map and db_field_map[db_col] != field_value:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Field key collision after normalization: {field_key} -> {db_col}",
                    )
                db_field_map[db_col] = field_value

            # Add one SQL column per normalized field for this document type table.
            for db_col in db_field_map:
                cursor.execute(
                    sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} TEXT").format(
                        sql.Identifier(table_name),
                        sql.Identifier(db_col),
                    )
                )

            metadata_columns = ["document_id", "document_type", "source_filename", "source"]
            dynamic_columns = list(db_field_map.keys())
            insert_columns = metadata_columns + dynamic_columns
            insert_values = [
                document_id,
                selected_document_type,
                str(doc.get("source_filename") or ""),
                "ui-review",
                *[db_field_map[c] for c in dynamic_columns],
            ]
            placeholders = [sql.Placeholder() for _ in insert_columns]

            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO {} ({}) VALUES ({})
                    RETURNING id
                    """
                ).format(
                    sql.Identifier(table_name),
                    sql.SQL(", ").join(sql.Identifier(c) for c in insert_columns),
                    sql.SQL(", ").join(placeholders),
                ),
                insert_values,
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="Failed to persist reviewed fields")
            record_id = str(row[0])

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to persist reviewed fields for document %s", document_id)
        raise HTTPException(status_code=500, detail=f"Failed to persist reviewed fields: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()

    _set_span_attrs({"idp.saved_field_count": len(normalized_fields), "idp.review_table": table_name})

    return SaveReviewResponse(
        document_id=document_id,
        document_type=selected_document_type,
        table_name=table_name,
        record_id=record_id,
        saved_field_count=len(normalized_fields),
    )


@router.get("/visualization/{document_id}")
@router.get("/documents/{document_id}/visualization")
def get_document_visualization(document_id: str, page: int = 1) -> StreamingResponse:
    _set_span_attrs(
        {
            "idp.operation": "get_document_visualization",
            "idp.document_id": document_id,
            "idp.page_number": page,
        }
    )
    image = get_storage().download_blob(document_id, Stage.ANNOTATED, f"_page_{page}.png")
    if image:
        return StreamingResponse(
            BytesIO(image),
            media_type="image/png",
            headers={"Content-Disposition": f"inline; filename=visualization_{document_id}_page_{page}.png"},
        )

    # Fallback: build overlays from existing ACU blob + raw PDF on demand.
    try:
        proc = _new_processor()
        doc = proc.dms_service.get_document(document_id=document_id) or {}
        acu_blob_path = doc.get("acu_result_blob_path")
        if acu_blob_path:
            candidate_containers = [app_config.azure.storage.container_name, "documents", "credit-ocr"]
            deduped_containers = list(dict.fromkeys(candidate_containers))
            acu_blob_bytes = None
            for container_name in deduped_containers:
                acu_blob_bytes = proc.dms_service.storage_client.download_bytes(
                    container=container_name,
                    blob_name=acu_blob_path,
                )
                if acu_blob_bytes:
                    break

            pdf_data = proc.dms_service.download_document(document_id=document_id)
            if acu_blob_bytes and pdf_data:
                parsed = json.loads(acu_blob_bytes.decode("utf-8"))
                acu_result = parsed.get("acu_result", parsed)
                annotated_pages = build_acu_annotated_pages(pdf_data=pdf_data, acu_result=acu_result)
                for page_num, image_bytes in annotated_pages.items():
                    proc.dms_service.storage_client.upload_bytes(
                        container="documents",
                        blob_name=f"annotated/{document_id}_page_{page_num}.png",
                        data=image_bytes,
                        content_type="image/png",
                    )
                image = annotated_pages.get(page)
    except Exception as exc:
        logger.warning("On-demand visualization build failed for %s page %s: %s", document_id, page, exc)

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
    _set_span_attrs(
        {
            "idp.operation": "get_document_page_image",
            "idp.document_id": document_id,
            "idp.page_number": page,
        }
    )
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
    _set_span_attrs({"idp.operation": "list_documents", "idp.limit": limit, "idp.offset": offset})
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
    _set_span_attrs({"idp.operation": "health_check"})
    services: Dict[str, str] = {}
    overall = "healthy"

    try:
        cfg = AppConfig()
        conn = psycopg2.connect(connect_timeout=3, **cfg.database.psycopg2_dsn)
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                _ = cursor.fetchone()
        conn.close()
        services["database"] = "healthy"
    except Exception as exc:
        services["database"] = f"unhealthy: {exc}"
        overall = "unhealthy"

    try:
        # Lightweight check only: do not create/modify containers on health.
        _ = get_storage().blob_service_client
        services["blob_storage"] = "healthy"
    except Exception as exc:
        services["blob_storage"] = f"unhealthy: {exc}"
        overall = "unhealthy"

    try:
        probe_result: Dict[str, str] = {"status": "degraded: celery check timeout"}

        def _celery_probe() -> None:
            try:
                inspector = celery_app.control.inspect(timeout=3)
                ping = inspector.ping() or {}
                if ping:
                    probe_result["status"] = "healthy"
                    return
                stats = inspector.stats() or {}
                if stats:
                    probe_result["status"] = "healthy"
                    return
                probe_result["status"] = "degraded: no active workers"
            except Exception as probe_exc:
                probe_result["status"] = f"degraded: {probe_exc}"

        t = threading.Thread(target=_celery_probe, daemon=True)
        t.start()
        t.join(timeout=4)

        celery_status = probe_result["status"]

        # Fallback: if inspect control-plane is flaky, treat worker path as healthy
        # when Redis broker itself is reachable from API process.
        if celery_status != "healthy":
            try:
                broker = app_config.redis.broker_url
                rc = redis.Redis.from_url(broker, socket_connect_timeout=2, socket_timeout=2)
                if rc.ping():
                    celery_status = "healthy"
            except Exception:
                pass

        services["celery"] = celery_status
        if services["celery"] != "healthy" and overall == "healthy":
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
