# src/storage/storage.py
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Dict, Optional

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobClient, BlobServiceClient


class Stage(Enum):
    RAW = "raw"
    ACU = "acu"          # <-- your pipeline stage
    ANNOTATED = "annotated"


class BlobStorage:
    _instance: Optional["BlobStorage"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._connection_string = None
        self._container_name = None
        self._bsc: Optional[BlobServiceClient] = None
        self._initialized_containers = set()
        self._container_lock = threading.Lock()
        self._initialized = True

    @property
    def connection_string(self) -> str:
        if self._connection_string is None:
            self._connection_string = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        return self._connection_string

    @property
    def container_name(self) -> str:
        if self._container_name is None:
            self._container_name = os.getenv("AZURE_BLOB_CONTAINER", "documents")
        return self._container_name

    @property
    def blob_service_client(self) -> BlobServiceClient:
        if self._bsc is None:
            self._bsc = BlobServiceClient.from_connection_string(self.connection_string)
        return self._bsc

    def _ensure_container_exists(self, container_name: str) -> None:
        if container_name in self._initialized_containers:
            return
        with self._container_lock:
            if container_name in self._initialized_containers:
                return
            try:
                self.blob_service_client.get_container_client(container_name).create_container()
            except ResourceExistsError:
                pass
            self._initialized_containers.add(container_name)

    def ensure_all_containers_ready(self) -> None:
        self._ensure_container_exists(self.container_name)

    def blob_path(self, doc_id: str, stage: Stage, ext: str) -> PurePosixPath:
        if not ext.startswith(".") and not ext.startswith("_"):
            ext = f".{ext}"
        return PurePosixPath(f"{stage.value}/{doc_id}{ext}")

    def blob_client(self, doc_id: str, stage: Stage, ext: str) -> BlobClient:
        self._ensure_container_exists(self.container_name)
        cc = self.blob_service_client.get_container_client(self.container_name)
        return cc.get_blob_client(str(self.blob_path(doc_id, stage, ext)))

    def upload_blob(self, doc_id: str, stage: Stage, ext: str, data: bytes, overwrite: bool = True) -> None:
        bc = self.blob_client(doc_id, stage, ext)
        bc.upload_blob(data, overwrite=overwrite)

    def download_blob(self, doc_id: str, stage: Stage, ext: str) -> Optional[bytes]:
        try:
            bc = self.blob_client(doc_id, stage, ext)
            return bc.download_blob().readall()
        except Exception:
            return None

    def upload_document_data(
        self,
        doc_id: str,
        stage: Stage,
        ext: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        overwrite: bool = True,
    ) -> None:
        payload = {
            "document_id": doc_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
            "metadata": metadata or {},
        }
        self.upload_blob(doc_id, stage, ext, json.dumps(payload, indent=2).encode("utf-8"), overwrite=overwrite)


def get_storage() -> BlobStorage:
    return BlobStorage()
