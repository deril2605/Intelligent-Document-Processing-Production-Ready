CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- File info
    source_filename VARCHAR(255) NOT NULL,
    blob_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(100),

    -- Business context
    document_type VARCHAR(100),
    linked_entity VARCHAR(100),
    linked_entity_id VARCHAR(100),

    -- Integrity
    hash_sha256 VARCHAR(64),

    -- Pipeline status
    text_extraction_status VARCHAR(50)
        DEFAULT 'not ready'
        CHECK (text_extraction_status IN ('not ready', 'ready', 'in progress', 'completed', 'failed')),

    processing_status VARCHAR(50)
        DEFAULT 'pending extraction'
        CHECK (processing_status IN ('pending extraction', 'acu running', 'done', 'failed')),

    -- ACU reference
    acu_result_blob_path VARCHAR(500),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_blob_path ON documents(blob_path);
CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON documents(processing_status);

-- Tracks each processing attempt (Celery task run) for a document
CREATE TABLE IF NOT EXISTS extraction_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    -- Celery task id (lets you correlate Celery logs / retries)
    celery_task_id VARCHAR(255),

    -- Job state (separate from documents.processing_status)
    status VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),

    -- What ran
    analyzer_id VARCHAR(200),

    -- Result pointer (optional: keep per-job result, even if document has latest pointer)
    acu_result_blob_path VARCHAR(500),

    -- Error info
    error_message TEXT,

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_document_id ON extraction_jobs(document_id);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_status ON extraction_jobs(status);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_celery_task_id ON extraction_jobs(celery_task_id);

