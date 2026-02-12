# src/dms/service.py

from __future__ import annotations

import hashlib
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

from .interfaces import StorageClient, MetadataRepository

logger = logging.getLogger(__name__)


class DmsService:
    def __init__(self, storage_client: StorageClient, metadata_repository: MetadataRepository) -> None:
        self.storage_client = storage_client
        self.metadata_repository = metadata_repository

    def _sha256_bytes(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def upload_document(
        self,
        *,
        file_path: Path,
        document_type: str,
        source_filename: Optional[str] = None,
        container: str = "documents",
    ) -> str:
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        if source_filename is None:
            source_filename = file_path.name

        data = file_path.read_bytes()
        file_size = len(data)

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        document_id = str(uuid.uuid4())
        file_hash = self._sha256_bytes(data)

        ext = file_path.suffix or ".bin"
        blob_path = f"raw/{document_type}/{document_id}{ext}"

        # Upload bytes to Azure Blob (cloud)
        self.storage_client.upload_bytes(
            container=container,
            blob_name=blob_path,
            data=data,
            content_type=mime_type,
        )

        # Determine readiness
        allowed_mime_types = {"application/pdf", "image/png", "image/jpeg"}
        is_ready = mime_type in allowed_mime_types

        text_extraction_status = "ready" if is_ready else "not ready"
        processing_status = "pending extraction"

        # Insert metadata row (MATCHES YOUR REAL DB COLUMNS)
        self.metadata_repository.insert_document(
            document_id=document_id,
            blob_path=blob_path,
            source_filename=source_filename,
            file_size=file_size,
            mime_type=mime_type,
            document_type=document_type,
            hash_sha256=file_hash,
            linked_entity=None,
            linked_entity_id=None,
            text_extraction_status=text_extraction_status,
            processing_status=processing_status,
            acu_result_blob_path=None,
        )

        logger.info("Uploaded document %s -> %s", document_id, blob_path)
        return document_id

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        return self.metadata_repository.get_document(document_id=document_id)

    def download_document(self, *, document_id: str, container: str = "documents") -> Optional[bytes]:
        doc = self.get_document(document_id)
        if not doc:
            return None
        return self.storage_client.download_bytes(container=container, blob_name=doc["blob_path"])

    def list_documents_by_type(self, *, document_type: str) -> List[Dict[str, Any]]:
        return self.metadata_repository.list_documents_by_type(document_type=document_type)

    def update_textextraction_status(self, *, document_id: str, status: str) -> bool:
        valid = {"not ready", "ready", "in progress", "completed", "failed"}
        if status not in valid:
            raise ValueError(f"Invalid status. Must be one of: {sorted(valid)}")
        return self.metadata_repository.update_document_status(document_id=document_id, status=status)

    def mark_ocr_running(self, *, document_id: str) -> bool:
        return self.metadata_repository.update_processing_status(document_id=document_id, status="ocr running")

    def mark_llm_running(self, *, document_id: str) -> bool:
        return self.metadata_repository.update_processing_status(document_id=document_id, status="llm running")

    def mark_processing_done(self, *, document_id: str) -> bool:
        return self.metadata_repository.update_processing_status(document_id=document_id, status="done")

    def update_acu_result_blob_path(self, *, document_id: str, acu_result_blob_path: str) -> bool:
        return self.metadata_repository.update_acu_result_blob_path(
            document_id=document_id,
            acu_result_blob_path=acu_result_blob_path,
        )
