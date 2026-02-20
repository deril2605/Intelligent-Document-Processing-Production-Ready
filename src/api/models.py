from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    OCR_RUNNING = "ocr_running"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentUploadResponse(BaseModel):
    document_id: str
    source_filename: str
    document_type: str
    classification_status: Optional[str] = None
    classification_error: Optional[str] = None
    classified_document_type: Optional[str] = None
    classifier_confidence: Optional[float] = None
    classification_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    status: Dict[str, Any]
    task_id: Optional[str] = None


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: ProcessingStatus
    document_type: Optional[str] = None
    classification_status: Optional[str] = None
    classified_document_type: Optional[str] = None
    classifier_confidence: Optional[float] = None
    classification_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    text_extraction_status: Optional[str] = None
    processing_status: Optional[str] = None
    extraction_jobs: List[Dict[str, Any]] = Field(default_factory=list)
    acu_result_blob_path: Optional[str] = None
    filename: Optional[str] = None
    upload_timestamp: Optional[datetime] = None
    error_message: Optional[str] = None


class DocumentResultsResponse(BaseModel):
    document_id: str
    status: ProcessingStatus
    document_type: Optional[str] = None
    acu_result_blob_path: Optional[str] = None
    acu_result: Dict[str, Any] = Field(default_factory=dict)
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    has_visualization: bool = False
    total_pages: Optional[int] = None


class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Optional[str] = None


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: datetime
    services: Dict[str, str]


class SaveReviewRequest(BaseModel):
    document_type: str
    normalized_fields: Dict[str, str] = Field(default_factory=dict)


class SaveReviewResponse(BaseModel):
    document_id: str
    document_type: str
    table_name: str
    record_id: str
    saved_field_count: int
