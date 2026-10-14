ALTER TABLE schemes ADD COLUMN IF NOT EXISTS application_procedure JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE schemes
SET description = 'Income support scheme for landholding farmer families. The State/UT identifies families using land records; the central portal provides registration and beneficiary status services.',
    benefit_description = '₹6,000 per year in three equal installments, subject to the published exclusions and government verification.',
    eligibility_rules = '{
      "required": [{"field":"landholding_family","operator":"eq","value":true,"label":"The applicant belongs to a farmer family that owns cultivable land in the relevant State/UT land records.","evidence_url":"https://pmkisan.gov.in/Documents/RevisedPM-KISANOperationalGuidelines%28English%29.pdf"}],
      "excluded_if": [
        {"field":"institutional_landholder","operator":"eq","value":true,"label":"Institutional landholders are excluded."},
        {"field":"constitutional_post_holder","operator":"eq","value":true,"label":"A family member is a former or present constitutional post holder."},
        {"field":"elected_office_exclusion","operator":"eq","value":true,"label":"A family member falls in a listed elected-office exclusion category."},
        {"field":"government_employee_exclusion","operator":"eq","value":true,"label":"A family member falls in a listed government/PSE/local-body employee or retiree exclusion category."},
        {"field":"pension_10000_exclusion","operator":"eq","value":true,"label":"A covered superannuated/retired pensioner receives a monthly pension of INR 10,000 or more (with the guideline''s stated staff-category exception)."},
        {"field":"income_tax_payer_exclusion","operator":"eq","value":true,"label":"A family member paid income tax in the last assessment year."},
        {"field":"practicing_registered_professional_exclusion","operator":"eq","value":true,"label":"A family member is a registered practicing professional in a listed profession."}
      ],
      "official_review_if": [{"field":"land_acquired_after_2019_02_01","operator":"eq","value":true,"label":"The official portal identifies some post-01-02-2019 land acquisitions as cases that may be withheld pending physical verification; this is an official review flag, not an automatic ineligibility rule.","evidence_url":"https://pmkisan.gov.in/"}],
      "family_definition":"Husband, wife and minor children; confirm interpretation and land-record evidence with the State/UT authority."
    }'::jsonb,
    exclusion_rules = '["Institutional landholders","Specified constitutional/elected office holders","Specified government/PSE/local-body employees and retirees, with stated exceptions","Covered pensioners receiving INR 10,000 or more per month","Persons who paid income tax in the last assessment year","Registered professionals carrying out the listed profession"]'::jsonb,
    document_checklist = '[{"item":"State/UT cultivable land record","status":"official_basis","note":"The exact accepted record and verification process are State/UT administered."},{"item":"eKYC for registered beneficiaries","status":"required","note":"The official portal states eKYC is mandatory for registered PM-KISAN farmers."}]'::jsonb,
    application_procedure = '["Use the official PM-KISAN New Farmer Registration service or the State/UT process.","State/UT authorities identify beneficiaries against land records.","Complete eKYC if registered as a beneficiary.","Use the official Know Your Status service for registration/payment status; CropAI does not request or process OTPs."]'::jsonb,
    application_status = 'unknown',
    application_open_date = NULL,
    deadline = NULL,
    date_precision = NULL,
    verification_status = 'verified',
    source_published_at = NULL,
    last_checked_at = '2026-10-12 10:33:07+00'::timestamptz,
    evidence_notes = 'Verified from the official PM-KISAN portal (scheme summary, exclusions, current portal notices, New Farmer Registration and eKYC notice) and the official Revised Operational Guidelines PDF. The portal''s post-01-02-2019 land-acquisition notice describes suspected cases withheld pending physical verification; this record does not treat it as a categorical exclusion. Benefit is subject to government verification. Application window/deadline not verified; official authority is final.'
WHERE scheme_id = 'pm-kisan';
