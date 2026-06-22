-- Add raw markdown document storage; remove unused JSONB metadata columns

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS raw_markdown TEXT;

ALTER TABLE documents
    DROP COLUMN IF EXISTS raw_metadata,
    DROP COLUMN IF EXISTS extraction_metadata;
