# src/tasks/pipeline_tasks.py

from __future__ import annotations

import asyncio
import logging
from celery import chain
import os
from typing import Optional

import psycopg2
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.propagate import extract, inject

from src.celery_app import celery_app
from src.dms.service import DmsService
from src.dms.adapters import AzureBlobStorageClient, PostgresMetadataRepository

# You will implement these in YOUR integration layer:
# - process_document_with_acu: runs ACU, writes result JSON to blob, updates acu_result_blob_path, status, job, etc.
# - (optional) postprocess_acu_result: anything after ACU (normalization/DB persist/etc.)
from src.integration.pipeline import process_document_with_acu  # <-- create this

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
load_dotenv()


def _get_dms_service() -> DmsService:
    """Create a DmsService instance for Celery workers (Azure Blob cloud + Postgres)."""
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    blob_service_client = BlobServiceClient.from_connection_string(conn_str)

    pg_conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "dms_meta"),
        user=os.getenv("PGUSER", "dms"),
        password=os.getenv("PGPASSWORD", "dms"),
    )
    try:
        pg_conn.autocommit = True
    except Exception:
        pass

    storage_client = AzureBlobStorageClient(blob_service_client)
    metadata_repo = PostgresMetadataRepository(pg_conn)
    return DmsService(storage_client=storage_client, metadata_repository=metadata_repo)


def _resolve_job_id(dms_service: DmsService, *, document_id: str, job_id: Optional[str]) -> Optional[str]:
    if job_id:
        return job_id

    try:
        jobs = dms_service.get_extraction_jobs(document_id=document_id)
        if jobs:
            return jobs[0].get("id")  # assumes list ordered newest-first in your adapter
    except Exception:
        logger.exception("Failed resolving latest extraction job for %s", document_id)
    return None


def _mark_job_status(
    dms_service: DmsService,
    *,
    document_id: str,
    job_id: Optional[str],
    status: str,
    error_message: Optional[str] = None,
) -> None:
    resolved_job_id = _resolve_job_id(dms_service, document_id=document_id, job_id=job_id)
    if not resolved_job_id:
        return
    dms_service.update_extraction_job(job_id=resolved_job_id, status=status, error_message=error_message)


def _mark_job_failed(
    dms_service: DmsService,
    *,
    document_id: str,
    error_message: str,
    job_id: Optional[str] = None,
) -> None:
    """Best-effort: mark extraction job failed + document failed."""
    try:
        _mark_job_status(
            dms_service,
            document_id=document_id,
            job_id=job_id,
            status="failed",
            error_message=error_message,
        )
    except Exception:
        logger.exception("Failed updating extraction job to failed for %s", document_id)

    try:
        dms_service.mark_processing_failed(document_id=document_id)
    except Exception:
        logger.exception("Failed updating processing_status to failed for %s", document_id)


def _request_headers(task) -> dict:
    headers = getattr(getattr(task, "request", None), "headers", None)
    return headers if isinstance(headers, dict) else {}


def _current_trace_headers() -> dict:
    headers: dict = {}
    inject(headers)
    return headers


@celery_app.task(bind=True)
def process_acu_task(self, *, document_id: str, job_id: Optional[str] = None) -> str:
    """
    Celery task: download raw doc bytes from blob -> run ACU -> store ACU JSON -> update statuses.
    """
    task_name = "process_acu_task"
    parent_ctx = extract(_request_headers(self))
    with tracer.start_as_current_span(
        task_name,
        context=parent_ctx,
        attributes={
            "document.id": document_id,
            "celery.task_id": str(getattr(self.request, "id", "")),
        },
    ):
        logger.info("Starting %s for document %s", task_name, document_id)

        dms_service = _get_dms_service()

        try:
            doc = dms_service.get_document(document_id=document_id)
            if not doc:
                raise ValueError(f"Document {document_id} not found")

            blob_data = dms_service.download_document(document_id=document_id)
            if not blob_data:
                raise ValueError(f"Could not download document {document_id} from blob")

            # Mark job stage running
            _mark_job_status(dms_service, document_id=document_id, job_id=job_id, status="running")

            # Mark stage running (YOUR schema uses 'acu running')
            dms_service.mark_acu_running(document_id=document_id)

            # Run ACU pipeline (async-friendly)
            asyncio.run(process_document_with_acu(document_id=document_id, pdf_data=blob_data, dms_service=dms_service))

            # Mark extraction job success
            _mark_job_status(dms_service, document_id=document_id, job_id=job_id, status="done")

            logger.info("Completed %s for document %s", task_name, document_id)
            return document_id

        except Exception as e:
            error_message = f"{task_name} failed for {document_id}: {e}"
            logger.exception(error_message)
            _mark_job_failed(dms_service, document_id=document_id, error_message=error_message, job_id=job_id)
            raise


@celery_app.task(bind=True)
def run_full_pipeline_task(self, *, document_id: str, job_id: Optional[str] = None) -> str:
    """
    Celery task: run the full pipeline (currently just ACU; later you can chain more).
    """
    task_name = "run_full_pipeline_task"
    parent_ctx = extract(_request_headers(self))
    with tracer.start_as_current_span(
        task_name,
        context=parent_ctx,
        attributes={
            "document.id": document_id,
            "celery.task_id": str(getattr(self.request, "id", "")),
        },
    ):
        logger.info("Starting %s for document %s", task_name, document_id)

        try:
            child_headers = _current_trace_headers()
            pipeline = chain(
                process_acu_task.s(document_id=document_id, job_id=job_id).set(headers=child_headers),
                # Later:
                # process_llm_task.s(),
                # etc.
            )
            pipeline.apply_async()
            logger.info("Initiated %s for document %s", task_name, document_id)
            return document_id

        except Exception as e:
            dms_service = _get_dms_service()
            error_message = f"{task_name} failed for {document_id}: {e}"
            logger.exception(error_message)
            _mark_job_failed(dms_service, document_id=document_id, error_message=error_message, job_id=job_id)
            raise


@celery_app.task(bind=True)
def process_document_async(self, *, document_id: str) -> str:
    """
    Main entrypoint used by AsyncDocumentProcessor.trigger_processing().
    Creates/ensures a job, then triggers pipeline.
    """
    task_name = "process_document_async"
    parent_ctx = extract(_request_headers(self))
    with tracer.start_as_current_span(
        task_name,
        context=parent_ctx,
        attributes={
            "document.id": document_id,
            "celery.task_id": str(getattr(self.request, "id", "")),
        },
    ):
        logger.info("Starting %s for document %s", task_name, document_id)

        dms_service = _get_dms_service()

        try:
            job_id: Optional[str] = None
            doc = dms_service.get_document(document_id=document_id)
            if not doc:
                raise ValueError(f"Document {document_id} not found")

            if doc.get("text_extraction_status") != "ready":
                raise ValueError(f"Document {document_id} not ready (text_extraction_status={doc.get('text_extraction_status')})")

            # Ensure an extraction job exists (your DB constraint expects status like 'pending' not 'pending extraction')
            try:
                job_id = dms_service.create_extraction_job(document_id=document_id, status="pending")
            except Exception:
                # ok if you already created one at upload time
                logger.info("Could not create job (may already exist) for %s", document_id, exc_info=True)
                job_id = _resolve_job_id(dms_service, document_id=document_id, job_id=None)

            child_headers = _current_trace_headers()
            run_full_pipeline_task.apply_async(
                kwargs={"document_id": document_id, "job_id": job_id},
                headers=child_headers,
            )
            logger.info("Queued full pipeline for document %s", document_id)
            return document_id

        except Exception as e:
            error_message = f"{task_name} failed for {document_id}: {e}"
            logger.exception(error_message)
            _mark_job_failed(dms_service, document_id=document_id, error_message=error_message, job_id=None)
            raise
