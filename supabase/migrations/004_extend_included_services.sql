-- Extend included_services for Allowances and Ancillary Charges; remove fee rows from contract_terms

ALTER TABLE included_services
    ADD COLUMN IF NOT EXISTS source_section TEXT NOT NULL DEFAULT 'included_services'
        CHECK (source_section IN ('included_services', 'allowances_fees'));

ALTER TABLE included_services
    ADD COLUMN IF NOT EXISTS fee_type TEXT
        CHECK (fee_type IS NULL OR fee_type IN ('allowance', 'ancillary_fee'));

ALTER TABLE included_services
    ADD COLUMN IF NOT EXISTS value_type TEXT
        CHECK (value_type IS NULL OR value_type IN (
            'numeric', 'included', 'quoted_upon_request', 'pass_through', 'text'
        ));

ALTER TABLE included_services
    ADD COLUMN IF NOT EXISTS value_text TEXT;

ALTER TABLE included_services
    ADD COLUMN IF NOT EXISTS value_numeric NUMERIC;

ALTER TABLE included_services
    ADD COLUMN IF NOT EXISTS basis_type TEXT
        CHECK (basis_type IS NULL OR basis_type IN (
            'awp_minus_percent', 'dollar_per_claim', 'pmpm', 'pmpy',
            'per_record', 'per_audit', 'per_hour', 'flat_annual',
            'per_member', 'per_member_per_year', 'per_brand_drug', 'other'
        ));

ALTER TABLE included_services
    ADD COLUMN IF NOT EXISTS unit_label TEXT;

-- Migrate existing fee rows from contract_terms into included_services
INSERT INTO included_services (
    document_id,
    source_section,
    category,
    service_name,
    is_included,
    cost_summary,
    page_number,
    fee_type,
    value_type,
    value_text,
    value_numeric,
    basis_type,
    unit_label
)
SELECT
    document_id,
    'allowances_fees',
    COALESCE(section_title, 'General'),
    COALESCE(source_row_label, value_text),
    value_type = 'included',
    value_text,
    page_number,
    CASE
        WHEN term_category = 'allowance' THEN 'allowance'
        ELSE 'ancillary_fee'
    END,
    value_type,
    value_text,
    value_numeric,
    basis_type,
    unit_label
FROM contract_terms
WHERE term_category IN ('allowance', 'ancillary_fee');

DELETE FROM contract_terms WHERE term_category IN ('allowance', 'ancillary_fee');

-- Tighten contract_terms term_category to pricing-grid terms only
ALTER TABLE contract_terms DROP CONSTRAINT IF EXISTS contract_terms_term_category_check;

ALTER TABLE contract_terms
    ADD CONSTRAINT contract_terms_term_category_check
    CHECK (term_category IN (
        'admin_fee', 'network_discount', 'dispensing_fee', 'rebate'
    ));

CREATE INDEX IF NOT EXISTS included_services_source_section_idx
    ON included_services (document_id, source_section);

CREATE UNIQUE INDEX IF NOT EXISTS included_services_natural_key_idx ON included_services (
    document_id,
    source_section,
    category,
    service_name,
    COALESCE(value_text, '')
);
