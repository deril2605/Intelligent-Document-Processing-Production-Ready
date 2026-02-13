# src/integration/async_processing.py

from __future__ import annotations

import logging
import os
from typing import Optional, Dict, Any

import psycopg2
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

from src.dms.service import DmsService
from src.dms.adapters import AzureBlobStorageClient, PostgresMetadataRepository

logger = logging.getLogger(__name__)

load_dotenv()


class AsyncDocumentProcessor:
    """Service for triggering async document processing (YOUR stack: Azure Blob cloud + Postgres + ACU)."""

    def __init__(self) -> None:
        # --- Azure Blob (cloud) ---
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not conn_str:
            raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

        blob_service_client = BlobServiceClient.from_connection_string(conn_str)

        # Optional: ensure container exists (safe to ignore errors if it already exists)
        container = os.getenv("AZURE_BLOB_CONTAINER", "documents")
        try:
            blob_service_client.create_container(container)
        except Exception:
            pass

        # --- Postgres ---
        pg_conn = psycopg2.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=int(os.getenv("PGPORT", "5432")),
            dbname=os.getenv("PGDATABASE", "dms_meta"),
            user=os.getenv("PGUSER", "dms"),
            password=os.getenv("PGPASSWORD","dms"),
        )
        try:
            pg_conn.autocommit = True
        except Exception:
            pass

        storage_client = AzureBlobStorageClient(blob_service_client)
        metadata_repo = PostgresMetadataRepository(pg_conn)

        self.dms_service = DmsService(storage_client=storage_client, metadata_repository=metadata_repo)

    def trigger_processing(self, *, document_id: str) -> Optional[str]:
        """
        Trigger async processing for a document (Celery task).
        Returns task_id if triggered, else None.
        """
        try:
            doc = self.dms_service.get_document(document_id=document_id)
            if not doc:
                logger.error("Document %s not found", document_id)
                return None

            # your DB column name is text_extraction_status
            if doc.get("text_extraction_status") != "ready":
                logger.warning(
                    "Document %s not ready (text_extraction_status=%s)",
                    document_id,
                    doc.get("text_extraction_status"),
                )
                return None

            # Import dynamically to avoid circular imports
            from src.tasks.pipeline_tasks import process_document_async

            task = process_document_async.delay(document_id=document_id)
            logger.info("Triggered async processing for %s, task_id=%s", document_id, task.id)
            return task.id

        except Exception:
            logger.exception("Failed to trigger processing for %s", document_id)
            return None

    def get_processing_status(self, *, document_id: str) -> Dict[str, Any]:
        """
        Read current status from Postgres (author-style).
        """
        try:
            doc = self.dms_service.get_document(document_id=document_id)
            if not doc:
                return {"error": "Document not found"}

            jobs = self.dms_service.get_extraction_jobs(document_id=document_id)

            return {
                "document_id": document_id,
                "text_extraction_status": doc.get("text_extraction_status"),
                "processing_status": doc.get("processing_status"),
                "extraction_jobs": jobs,
                "acu_result_blob_path": doc.get("acu_result_blob_path"),
            }

        except Exception as e:
            logger.exception("Failed to get status for %s", document_id)
            return {"error": str(e)}
