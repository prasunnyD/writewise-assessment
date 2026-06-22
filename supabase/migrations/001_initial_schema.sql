-- WriteWise contract extraction schema

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS pricing_models (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

INSERT INTO pricing_models (id, display_name) VALUES
    ('traditional', 'Traditional Pricing'),
    ('applied_rebates', 'Traditional Pricing — Applied Rebates')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS networks (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

INSERT INTO networks (id, display_name) VALUES
    ('broad_national', 'Broad National Network'),
    ('retail_30', 'Retail 30'),
    ('retail_90', 'Retail 90'),
    ('mail', 'Mail Order'),
    ('retail_specialty', 'Retail Specialty'),
    ('exclusive_specialty', 'Exclusive Specialty'),
    ('northwind_direct_specialty', 'Northwind Direct Specialty')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_filename TEXT NOT NULL,
    vendor_name TEXT,
    client_name TEXT,
    proposal_date DATE,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_metadata JSONB DEFAULT '{}'::jsonb,
    extraction_metadata JSONB DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS documents_source_filename_idx
    ON documents (source_filename);

CREATE TABLE IF NOT EXISTS contract_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    pricing_model_id TEXT REFERENCES pricing_models(id),
    network_id TEXT REFERENCES networks(id),
    term_category TEXT NOT NULL CHECK (term_category IN (
        'admin_fee', 'network_discount', 'dispensing_fee',
        'rebate', 'allowance', 'ancillary_fee'
    )),
    drug_type TEXT CHECK (drug_type IN (
        'brand', 'generic', 'ldd', 'new_to_market'
    )),
    channel TEXT CHECK (channel IN (
        'retail_30', 'retail_90', 'mail', 'specialty'
    )),
    calendar_year INTEGER,
    payment_schedule TEXT CHECK (payment_schedule IN (
        'quarterly_150d', 'monthly_60d'
    )),
    payment_timing_text TEXT,
    formulary_name TEXT,
    value_type TEXT NOT NULL CHECK (value_type IN (
        'numeric', 'included', 'quoted_upon_request', 'pass_through', 'text'
    )),
    value_text TEXT NOT NULL,
    value_numeric NUMERIC,
    basis_type TEXT CHECK (basis_type IN (
        'awp_minus_percent', 'dollar_per_claim', 'pmpm', 'pmpy',
        'per_record', 'per_audit', 'per_hour', 'flat_annual',
        'per_member', 'per_member_per_year', 'per_brand_drug', 'other'
    )),
    unit_label TEXT,
    section_title TEXT,
    page_number INTEGER,
    source_row_label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS contract_terms_document_idx ON contract_terms (document_id);
CREATE INDEX IF NOT EXISTS contract_terms_lookup_idx ON contract_terms (
    document_id, term_category, pricing_model_id, network_id, calendar_year
);

CREATE UNIQUE INDEX IF NOT EXISTS contract_terms_natural_key_idx ON contract_terms (
    document_id,
    COALESCE(pricing_model_id, ''),
    COALESCE(network_id, ''),
    term_category,
    COALESCE(drug_type, ''),
    COALESCE(channel, ''),
    COALESCE(calendar_year, -1),
    COALESCE(payment_schedule, ''),
    COALESCE(source_row_label, ''),
    value_text
);

CREATE TABLE IF NOT EXISTS included_services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    service_name TEXT NOT NULL,
    is_included BOOLEAN NOT NULL DEFAULT TRUE,
    cost_summary TEXT,
    page_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS included_services_document_idx ON included_services (document_id);

CREATE TABLE IF NOT EXISTS assumptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    bullet_text TEXT NOT NULL,
    page_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS assumptions_document_idx ON assumptions (document_id);
