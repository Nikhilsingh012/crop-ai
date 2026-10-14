ALTER TABLE source_registry ADD COLUMN IF NOT EXISTS last_content_sha256 TEXT;
ALTER TABLE source_registry ADD COLUMN IF NOT EXISTS last_http_status INTEGER;
ALTER TABLE source_registry ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

INSERT INTO source_registry(source_key,source_name,source_url,source_type,retrieval_method,polling_policy,enabled) VALUES
 ('pm-kisan','PM-KISAN official portal','https://pmkisan.gov.in/','scheme','manual-http-check','manual-review',FALSE),
 ('pmfby','PMFBY official policy page','https://www.pmfby.gov.in/policy','scheme','manual-http-check','manual-review',FALSE),
 ('pm-kusum','PM-KUSUM official portal','https://pmkusum.mnre.gov.in/','scheme','manual-http-check','manual-review',FALSE),
 ('aif','Agriculture Infrastructure Fund official portal','https://agriinfra.dac.gov.in/','scheme','manual-http-check','manual-review',FALSE),
 ('enam','e-NAM official portal','https://enam.gov.in/','market','manual-http-check','manual-review',FALSE)
ON CONFLICT(source_key) DO NOTHING;
