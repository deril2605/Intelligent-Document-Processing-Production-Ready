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

from src.celery_app import celery_app
from src.dms.service import DmsService
from src.dms.adapters import AzureBlobStorageClient, PostgresMetadataRepository

# You will implement these in YOUR integration layer:
# - process_document_with_acu: runs ACU, writes result JSON to blob, updates acu_result_blob_path, status, job, etc.
# - (optional) postprocess_acu_result: anything after ACU (normalization/DB persist/etc.)
from src.integration.pipeline import process_document_with_acu  # <-- create this

logger = logging.getLogger(__name__)
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


def _mark_job_failed(dms_service: DmsService, *, document_id: str, error_message: str) -> None:
    """Best-effort: mark latest extraction job failed + document failed."""
    try:
        jobs = dms_service.get_extraction_jobs(document_id=document_id)
        if jobs:
            job_id = jobs[0].get("id")  # assumes list ordered newest-first in your adapter
            if job_id:
                dms_service.update_extraction_job(job_id=job_id, status="failed", error_message=error_message)
    except Exception:
        logger.exception("Failed updating extraction job to failed for %s", document_id)

    try:
        dms_service.mark_processing_failed(document_id=document_id)
    except Exception:
        logger.exception("Failed updating processing_status to failed for %s", document_id)


@celery_app.task(bind=True)
def process_acu_task(self, *, document_id: str) -> str:
    """
    Celery task: download raw doc bytes from blob -> run ACU -> store ACU JSON -> update statuses.
    """
    task_name = "process_acu_task"
    logger.info("Starting %s for document %s", task_name, document_id)

    dms_service = _get_dms_service()

    try:
        doc = dms_service.get_document(document_id=document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        blob_data = dms_service.download_document(document_id=document_id)
        if not blob_data:
            raise ValueError(f"Could not download document {document_id} from blob")

        # Mark stage running (YOUR schema uses 'acu running')
        dms_service.mark_acu_running(document_id=document_id)

        # Run ACU pipeline (async-friendly)
        asyncio.run(process_document_with_acu(document_id=document_id, pdf_data=blob_data, dms_service=dms_service))

        logger.info("Completed %s for document %s", task_name, document_id)
        return document_id

    except Exception as e:
        error_message = f"{task_name} failed for {document_id}: {e}"
        logger.exception(error_message)
        _mark_job_failed(dms_service, document_id=document_id, error_message=error_message)
        raise


@celery_app.task(bind=True)
def run_full_pipeline_task(self, *, document_id: str) -> str:
    """
    Celery task: run the full pipeline (currently just ACU; later you can chain more).
    """
    task_name = "run_full_pipeline_task"
    logger.info("Starting %s for document %s", task_name, document_id)

    try:
        pipeline = chain(
            process_acu_task.s(document_id=document_id),
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
        _mark_job_failed(dms_service, document_id=document_id, error_message=error_message)
        raise


@celery_app.task(bind=True)
def process_document_async(self, *, document_id: str) -> str:
    """
    Main entrypoint used by AsyncDocumentProcessor.trigger_processing().
    Creates/ensures a job, then triggers pipeline.
    """
    task_name = "process_document_async"
    logger.info("Starting %s for document %s", task_name, document_id)

    dms_service = _get_dms_service()

    try:
        doc = dms_service.get_document(document_id=document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        if doc.get("text_extraction_status") != "ready":
            raise ValueError(f"Document {document_id} not ready (text_extraction_status={doc.get('text_extraction_status')})")

        # Ensure an extraction job exists (your DB constraint expects status like 'pending' not 'pending extraction')
        try:
            dms_service.create_extraction_job(document_id=document_id, status="pending")
        except Exception:
            # ok if you already created one at upload time
            logger.info("Could not create job (may already exist) for %s", document_id, exc_info=True)

        run_full_pipeline_task.delay(document_id=document_id)
        logger.info("Queued full pipeline for document %s", document_id)
        return document_id

    except Exception as e:
        error_message = f"{task_name} failed for {document_id}: {e}"
        logger.exception(error_message)
        _mark_job_failed(dms_service, document_id=document_id, error_message=error_message)
        raise
