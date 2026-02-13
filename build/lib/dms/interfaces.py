# src/dms/interfaces.py

from __future__ import annotations

from typing import Protocol, Optional, List, Dict, Any


class StorageClient(Protocol):
    def upload_bytes(
        self,
        *,
        container: str,
        blob_name: str,
        data: bytes,
        content_type: Optional[str] = None,
    ) -> None:
        ...

    def download_bytes(
        self,
        *,
        container: str,
        blob_name: str,
    ) -> Optional[bytes]:
        ...


class MetadataRepository(Protocol):
    # --- documents table ---
    def insert_document(
        self,
        *,
        document_id: str,
        blob_path: str,
        source_filename: str,
        file_size: int,
        mime_type: str,
        document_type: str,
        linked_entity: Optional[str],
        linked_entity_id: Optional[str],
        hash_sha256: str,
        text_extraction_status: str,
        processing_status: str,
        acu_result_blob_path: Optional[str],
    ) -> None:
        ...

    def get_document(self, *, document_id: str) -> Optional[Dict[str, Any]]:
        ...

    def list_documents_by_type(self, *, document_type: str) -> List[Dict[str, Any]]:
        ...

    def update_document_status(self, *, document_id: str, status: str) -> bool:
        ...

    def update_processing_status(self, *, document_id: str, status: str) -> bool:
        ...

    def update_acu_result_blob_path(self, *, document_id: str, acu_result_blob_path: str) -> bool:
        ...

    def list_documents_paginated(self, *, limit: int, offset: int) -> List[Dict[str, Any]]:
        ...

    # --- extraction_jobs table ---
    def insert_extraction_job(self, *, job_id: str, document_id: str, status: str) -> None:
        ...

    def update_extraction_job(self, *, job_id: str, status: str, error_message: Optional[str]) -> bool:
        ...

    def list_extraction_jobs(self, *, document_id: str) -> List[Dict[str, Any]]:
        ...
