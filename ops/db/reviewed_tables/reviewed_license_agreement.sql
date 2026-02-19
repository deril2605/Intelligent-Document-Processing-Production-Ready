CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS reviewed_license_agreement (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    document_type VARCHAR(100) NOT NULL,
    source_filename VARCHAR(255),
    source VARCHAR(30) NOT NULL DEFAULT 'ui-review',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- normalized outputs (editable/reviewed values) without suffix
    DocumentName TEXT,
    Parties TEXT,
    AgreementDate TEXT,
    EffectiveDate TEXT,
    ExpirationDate TEXT,
    RenewalTerm TEXT,
    NoticeToTerminateRenewal TEXT,
    GoverningLaw TEXT,
    LicenseGrant TEXT,
    Exclusivity TEXT,
    TerminationForConvenience TEXT
);

CREATE INDEX IF NOT EXISTS reviewed_license_agreement_document_id_idx
    ON reviewed_license_agreement(document_id);
