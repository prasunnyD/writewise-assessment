-- Remove vendor-specific network seed; networks are upserted during extraction

UPDATE contract_terms
    SET network_id = 'exclusive_specialty'
    WHERE network_id = 'northwind_direct_specialty';

DELETE FROM networks WHERE id = 'northwind_direct_specialty';

INSERT INTO networks (id, display_name) VALUES
    ('exclusive_specialty', 'Exclusive Specialty')
ON CONFLICT (id) DO NOTHING;
