# src/integration/pipeline.py

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from opentelemetry import trace

from src.config import AppConfig, get_hardcoded_analyzer_id
from src.dms.service import DmsService
from src.acu.client import AzureContentUnderstandingClient
from src.visualization import build_acu_annotated_pages

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


async def process_document_with_acu(
    *,
    document_id: str,
    pdf_data: bytes,
    dms_service: Optional[DmsService] = None,
    analyzer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run ACU on document bytes, persist ACU JSON to Azure Blob, update DB acu_result_blob_path,
    and update document status fields.
    """
    with tracer.start_as_current_span(
        "process_document_with_acu",
        attributes={
            "idp.document_id": document_id,
            "idp.has_dms_service": dms_service is not None,
        },
    ):
        cfg = AppConfig()

        resolved_doc_type = "unknown"
        if dms_service is not None:
            try:
                doc = dms_service.get_document(document_id=document_id)
                if doc and doc.get("document_type"):
                    resolved_doc_type = str(doc["document_type"])
            except Exception:
                pass

        if analyzer_id is None:
            analyzer_id = get_hardcoded_analyzer_id(resolved_doc_type) or cfg.acu.analyzer_id
        if not analyzer_id:
            raise ValueError(f"No analyzer configured for document_type='{resolved_doc_type}'")
        trace.get_current_span().set_attribute("idp.acu.analyzer_id", analyzer_id)
        trace.get_current_span().set_attribute("idp.document_type", resolved_doc_type)

        # Optional: mark processing status in DB
        if dms_service is not None:
            try:
                dms_service.mark_acu_running(document_id=document_id)
                dms_service.update_textextraction_status(document_id=document_id, status="in progress")
            except Exception as e:
                logger.warning("Failed to mark ACU running / in progress for %s: %s", document_id, e)

        # Build ACU client (API-key auth)
        acu_client = AzureContentUnderstandingClient(
            endpoint=cfg.acu.endpoint,
            api_version="2025-11-01",
            subscription_key=cfg.acu.api_key,
            token_provider=None,
            x_ms_useragent="azure-ai-content-understanding-python-sample-ga",
        )

        # Run ACU analyzeBinary with in-memory bytes
        with tracer.start_as_current_span("acu_analyze_binary"):
            analysis_response = acu_client.begin_analyze_binary(
                analyzer_id=analyzer_id,
                data=pdf_data,
            )
            acu_result: Dict[str, Any] = acu_client.poll_result(analysis_response)

        # Decide where to store ACU result JSON in blob
        doc_type = resolved_doc_type

        acu_result_blob_path = f"acu/{doc_type}/{document_id}.json"

        # Persist ACU result JSON to the SAME Azure Blob container (cloud)
        if dms_service is None:
            raise ValueError("dms_service is required to persist ACU output and update DB.")

        # Project standard: keep all stages under the single "documents" container.
        target_container = "documents"
        with tracer.start_as_current_span("blob_upload_acu_result"):
            dms_service.storage_client.upload_bytes(
                container=target_container,
                blob_name=acu_result_blob_path,
                data=_json_bytes(
                    {
                        "document_id": document_id,
                        "processing_timestamp": _utc_now_iso(),
                        "processing_metadata": {
                            "processing_method": "acu",
                            "analyzer_id": analyzer_id,
                            "api_version": "2025-11-01",
                        },
                        "acu_result": acu_result,
                    }
                ),
                content_type="application/json",
            )

        # Best effort: generate and persist per-page annotated overlays from *_raw fields.
        try:
            with tracer.start_as_current_span("build_and_upload_annotations"):
                annotated_pages = build_acu_annotated_pages(pdf_data=pdf_data, acu_result=acu_result)
                trace.get_current_span().set_attribute("idp.annotation.page_count", len(annotated_pages))
                for page_num, image_bytes in annotated_pages.items():
                    dms_service.storage_client.upload_bytes(
                        container=target_container,
                        blob_name=f"annotated/{document_id}_page_{page_num}.png",
                        data=image_bytes,
                        content_type="image/png",
                    )
                if annotated_pages:
                    logger.info("Generated %d annotated page(s) for document %s", len(annotated_pages), document_id)
        except Exception as e:
            logger.warning("Annotated visualization generation failed for %s: %s", document_id, e)

        # Update DB with result blob path
        try:
            dms_service.update_acu_result_blob_path(
                document_id=document_id,
                acu_result_blob_path=acu_result_blob_path,
            )
        except Exception as e:
            logger.warning("Failed to update acu_result_blob_path for %s: %s", document_id, e)

        # Mark statuses
        try:
            dms_service.update_textextraction_status(document_id=document_id, status="completed")
            dms_service.mark_processing_done(document_id=document_id)
        except Exception as e:
            logger.warning("Failed to mark completed/done for %s: %s", document_id, e)

        return {
            "document_id": document_id,
            "processing_timestamp": _utc_now_iso(),
            "acu_result_blob_path": acu_result_blob_path,
            "acu_result": acu_result,
        }
