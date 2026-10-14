-- Seed names and official landing pages only; no eligibility, benefit, deadline or status claims.
INSERT INTO schemes (scheme_id, official_name, government_level, official_source_url, official_application_url, application_status, verification_status)
VALUES
 ('pm-kisan','PM-KISAN','central','https://pmkisan.gov.in/','https://pmkisan.gov.in/','unknown','unverified'),
 ('pmfby','Pradhan Mantri Fasal Bima Yojana','central','https://www.pmfby.gov.in/policy','https://www.pmfby.gov.in/','unknown','unverified'),
 ('pm-kusum','PM-KUSUM','central','https://pmkusum.mnre.gov.in/','https://pmkusum.mnre.gov.in/','unknown','unverified'),
 ('aif','Agriculture Infrastructure Fund','central','https://agriinfra.dac.gov.in/','https://agriinfra.dac.gov.in/','unknown','unverified'),
 ('enam','e-NAM','central','https://enam.gov.in/','https://enam.gov.in/','unknown','unverified')
ON CONFLICT (scheme_id) DO NOTHING;

ALTER TABLE disease_reports ADD COLUMN IF NOT EXISTS report_dedupe_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_disease_reports_user_dedupe ON disease_reports(user_id, report_dedupe_key) WHERE report_dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_saved_schemes_user ON saved_schemes(user_id, saved_at DESC);
