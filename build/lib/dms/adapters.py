# src/dms/adapters.py

from __future__ import annotations

from typing import Optional, List, Dict, Any

from azure.storage.blob import BlobServiceClient, ContentSettings

from .interfaces import StorageClient, MetadataRepository


class AzureBlobStorageClient(StorageClient):
    def __init__(self, blob_service_client: BlobServiceClient) -> None:
        self._client = blob_service_client

    def upload_bytes(self, *, container: str, blob_name: str, data: bytes, content_type: Optional[str] = None) -> None:
        container_client = self._client.get_container_client(container)
        try:
            container_client.create_container()
        except Exception:
            pass

        blob_client = container_client.get_blob_client(blob_name)

        kwargs = {"overwrite": True}
        if content_type:
            kwargs["content_settings"] = ContentSettings(content_type=content_type)

        blob_client.upload_blob(data, **kwargs)

    def download_bytes(self, *, container: str, blob_name: str) -> Optional[bytes]:
        container_client = self._client.get_container_client(container)
        blob_client = container_client.get_blob_client(blob_name)
        try:
            stream = blob_client.download_blob()
            return stream.readall()
        except Exception:
            return None


class PostgresMetadataRepository(MetadataRepository):
    def __init__(self, connection) -> None:
        self._conn = connection
        try:
            self._conn.autocommit = True
        except Exception:
            pass

    def insert_document(
        self,
        *,
        document_id: str,
        blob_path: str,
        source_filename: str,
        file_size: int,
        mime_type: str,
        document_type: str,
        hash_sha256: str,
        linked_entity: Optional[str],
        linked_entity_id: Optional[str],
        text_extraction_status: str,
        processing_status: str,
        acu_result_blob_path: Optional[str] = None,
    ) -> None:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO documents (
                    id,
                    file_size,
                    mime_type,
                    document_type,
                    linked_entity,
                    linked_entity_id,
                    hash_sha256,
                    text_extraction_status,
                    processing_status,
                    source_filename,
                    blob_path,
                    acu_result_blob_path
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    file_size,
                    mime_type,
                    document_type,
                    linked_entity,
                    linked_entity_id,
                    hash_sha256,
                    text_extraction_status,
                    processing_status,
                    source_filename,
                    blob_path,
                    acu_result_blob_path,
                ),
            )

    def get_document(self, *, document_id: str) -> Optional[Dict[str, Any]]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    file_size,
                    created_at,
                    updated_at,
                    mime_type,
                    document_type,
                    linked_entity,
                    linked_entity_id,
                    hash_sha256,
                    text_extraction_status,
                    processing_status,
                    source_filename,
                    blob_path,
                    acu_result_blob_path
                FROM documents
                WHERE id = %s
                """,
                (document_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return {
                "id": row[0],
                "file_size": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "mime_type": row[4],
                "document_type": row[5],
                "linked_entity": row[6],
                "linked_entity_id": row[7],
                "hash_sha256": row[8],
                "text_extraction_status": row[9],
                "processing_status": row[10],
                "source_filename": row[11],
                "blob_path": row[12],
                "acu_result_blob_path": row[13],
            }

    def list_documents_by_type(self, *, document_type: str) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    file_size,
                    created_at,
                    updated_at,
                    mime_type,
                    document_type,
                    linked_entity,
                    linked_entity_id,
                    hash_sha256,
                    text_extraction_status,
                    processing_status,
                    source_filename,
                    blob_path,
                    acu_result_blob_path
                FROM documents
                WHERE document_type = %s
                ORDER BY created_at DESC
                """,
                (document_type,),
            )
            rows = cursor.fetchall()

        return [
            {
                "id": r[0],
                "file_size": r[1],
                "created_at": r[2],
                "updated_at": r[3],
                "mime_type": r[4],
                "document_type": r[5],
                "linked_entity": r[6],
                "linked_entity_id": r[7],
                "hash_sha256": r[8],
                "text_extraction_status": r[9],
                "processing_status": r[10],
                "source_filename": r[11],
                "blob_path": r[12],
                "acu_result_blob_path": r[13],
            }
            for r in rows
        ]

    def update_document_status(self, *, document_id: str, status: str) -> bool:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE documents
                SET text_extraction_status = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, document_id),
            )
            return cursor.rowcount > 0

    def update_processing_status(self, *, document_id: str, status: str) -> bool:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE documents
                SET processing_status = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, document_id),
            )
            return cursor.rowcount > 0

    def insert_extraction_job(self, *, job_id: str, document_id: str, status: str) -> None:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO extraction_jobs (id, document_id, status)
                VALUES (%s, %s, %s)
                """,
                (job_id, document_id, status),
            )

    def update_extraction_job(self, *, job_id: str, status: str, error_message: Optional[str]) -> bool:
        with self._conn.cursor() as cursor:
            if error_message is not None:
                cursor.execute(
                    """
                    UPDATE extraction_jobs
                    SET status = %s,
                        error_message = %s,
                        completed_at = CASE WHEN %s IN ('done', 'failed', 'finished') THEN NOW() ELSE completed_at END
                    WHERE id = %s
                    """,
                    (status, error_message, status, job_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE extraction_jobs
                    SET status = %s,
                        completed_at = CASE WHEN %s IN ('done', 'failed', 'finished') THEN NOW() ELSE completed_at END
                    WHERE id = %s
                    """,
                    (status, status, job_id),
                )
            return cursor.rowcount > 0

    def list_extraction_jobs(self, *, document_id: str) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, document_id, created_at, completed_at, status, error_message
                FROM extraction_jobs
                WHERE document_id = %s
                ORDER BY created_at DESC
                """,
                (document_id,),
            )
            rows = cursor.fetchall()

        return [
            {
                "id": r[0],
                "document_id": r[1],
                "created_at": r[2],
                "completed_at": r[3],
                "status": r[4],
                "error_message": r[5],
            }
            for r in rows
        ]

    def list_documents_paginated(self, *, limit: int, offset: int) -> List[Dict[str, Any]]:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    file_size,
                    created_at,
                    updated_at,
                    mime_type,
                    document_type,
                    linked_entity,
                    linked_entity_id,
                    hash_sha256,
                    text_extraction_status,
                    processing_status,
                    source_filename,
                    blob_path,
                    acu_result_blob_path
                FROM documents
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cursor.fetchall()

        return [
            {
                "id": r[0],
                "file_size": r[1],
                "created_at": r[2],
                "updated_at": r[3],
                "mime_type": r[4],
                "document_type": r[5],
                "linked_entity": r[6],
                "linked_entity_id": r[7],
                "hash_sha256": r[8],
                "text_extraction_status": r[9],
                "processing_status": r[10],
                "source_filename": r[11],
                "blob_path": r[12],
                "acu_result_blob_path": r[13],
            }
            for r in rows
        ]

    def update_acu_result_blob_path(self, *, document_id: str, acu_result_blob_path: str) -> bool:
        with self._conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE documents
                SET acu_result_blob_path = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (acu_result_blob_path, document_id),
            )
            return cursor.rowcount > 0
