-- Durable records for schemes, plans, farm economics, providers and opt-in reports.
-- Scheme and provider tables start empty; no deadlines or prices are fabricated.
CREATE TABLE IF NOT EXISTS source_registry (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    retrieval_method TEXT NOT NULL DEFAULT 'manual',
    polling_policy TEXT NOT NULL DEFAULT 'manual',
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_runs (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT REFERENCES source_registry(id) ON DELETE SET NULL,
    source_key TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    result TEXT NOT NULL CHECK (result IN ('no_update', 'update_found', 'failed', 'skipped')),
    error_code TEXT,
    records_seen INTEGER NOT NULL DEFAULT 0 CHECK (records_seen >= 0),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS schemes (
    scheme_id TEXT PRIMARY KEY,
    official_name TEXT NOT NULL,
    government_level TEXT NOT NULL CHECK (government_level IN ('central', 'state')),
    state_scope TEXT[],
    official_source_url TEXT NOT NULL,
    official_application_url TEXT,
    description TEXT,
    eligibility_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    exclusion_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    benefit_description TEXT,
    document_checklist JSONB NOT NULL DEFAULT '[]'::jsonb,
    application_open_date DATE,
    deadline DATE,
    date_precision TEXT,
    application_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK (application_status IN ('open', 'closed', 'continuous', 'unknown')),
    source_published_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('verified', 'stale', 'unverified')),
    evidence_notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scheme_updates (
    id BIGSERIAL PRIMARY KEY,
    scheme_id TEXT NOT NULL REFERENCES schemes(scheme_id) ON DELETE CASCADE,
    source_run_id BIGINT REFERENCES source_runs(id) ON DELETE SET NULL,
    changed_fields JSONB NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_url TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS saved_schemes (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scheme_id TEXT NOT NULL REFERENCES schemes(scheme_id) ON DELETE CASCADE,
    checklist_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, scheme_id)
);

CREATE TABLE IF NOT EXISTS farm_tasks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    farm_id BIGINT REFERENCES farms(id) ON DELETE CASCADE,
    crop_id BIGINT REFERENCES crops(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
    due_date DATE,
    reason TEXT,
    source_references JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_quality TEXT NOT NULL DEFAULT 'limited'
        CHECK (evidence_quality IN ('verified', 'limited', 'user_input')),
    valid_until TIMESTAMPTZ,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'completed', 'dismissed')),
    feedback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS farm_diary_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    farm_id BIGINT REFERENCES farms(id) ON DELETE CASCADE,
    crop_id BIGINT REFERENCES crops(id) ON DELETE SET NULL,
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    entry_type TEXT NOT NULL DEFAULT 'note',
    notes TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS farm_expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    farm_id BIGINT REFERENCES farms(id) ON DELETE CASCADE,
    crop_id BIGINT REFERENCES crops(id) ON DELETE SET NULL,
    season TEXT,
    category TEXT NOT NULL CHECK (category IN (
        'seeds', 'fertilizer', 'crop_protection', 'labor', 'machinery',
        'irrigation', 'equipment_rental', 'transport', 'other'
    )),
    description TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    quantity NUMERIC(14, 3) CHECK (quantity IS NULL OR quantity >= 0),
    quantity_unit TEXT,
    incurred_on DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS farm_sales (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    farm_id BIGINT REFERENCES farms(id) ON DELETE CASCADE,
    crop_id BIGINT REFERENCES crops(id) ON DELETE SET NULL,
    season TEXT,
    quantity NUMERIC(14, 3) NOT NULL CHECK (quantity > 0),
    quantity_unit TEXT NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    selling_cost NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (selling_cost >= 0),
    sold_on DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_prices (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    commodity TEXT NOT NULL,
    variety TEXT,
    state TEXT,
    district TEXT,
    mandi TEXT,
    observed_on DATE NOT NULL,
    minimum_price NUMERIC(14, 2) CHECK (minimum_price IS NULL OR minimum_price >= 0),
    modal_price NUMERIC(14, 2) CHECK (modal_price IS NULL OR modal_price >= 0),
    maximum_price NUMERIC(14, 2) CHECK (maximum_price IS NULL OR maximum_price >= 0),
    arrival_quantity NUMERIC(14, 3) CHECK (arrival_quantity IS NULL OR arrival_quantity >= 0),
    arrival_unit TEXT,
    price_unit TEXT NOT NULL DEFAULT 'INR/quintal',
    source_url TEXT NOT NULL,
    source_updated_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    freshness TEXT NOT NULL DEFAULT 'unverified'
        CHECK (freshness IN ('fresh', 'stale', 'unverified')),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS advisory_records (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    crop_id BIGINT REFERENCES crops(id) ON DELETE CASCADE,
    advisory_type TEXT NOT NULL CHECK (advisory_type IN ('irrigation', 'harvest')),
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL,
    source_references JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_quality TEXT NOT NULL DEFAULT 'limited'
        CHECK (evidence_quality IN ('verified', 'limited', 'insufficient')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS disease_reports (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    crop_id BIGINT REFERENCES crops(id) ON DELETE SET NULL,
    crop_name TEXT NOT NULL,
    growth_stage TEXT,
    symptom_category TEXT NOT NULL,
    report_date DATE NOT NULL DEFAULT CURRENT_DATE,
    state TEXT NOT NULL,
    district TEXT NOT NULL,
    coarse_area TEXT,
    private_image_key TEXT,
    weather_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    consent_to_aggregate BOOLEAN NOT NULL CHECK (consent_to_aggregate = TRUE),
    verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'under_review', 'expert_reviewed', 'rejected')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 days',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS regional_disease_alerts (
    id BIGSERIAL PRIMARY KEY,
    crop_name TEXT NOT NULL,
    symptom_category TEXT NOT NULL,
    state TEXT NOT NULL,
    district TEXT NOT NULL,
    report_count INTEGER NOT NULL CHECK (report_count >= 0),
    status TEXT NOT NULL DEFAULT 'community_signal'
        CHECK (status IN ('community_signal', 'under_review', 'expert_reviewed', 'confirmed', 'expired')),
    minimum_reports INTEGER NOT NULL CHECK (minimum_reports > 0),
    source_report_ids BIGINT[] NOT NULL DEFAULT '{}',
    valid_until TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (crop_name, symptom_category, state, district, valid_until)
);

CREATE INDEX IF NOT EXISTS idx_source_runs_source_started ON source_runs(source_key, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_schemes_state_status ON schemes(government_level, application_status, verification_status);
CREATE INDEX IF NOT EXISTS idx_farm_tasks_user_state_date ON farm_tasks(user_id, state, due_date);
CREATE INDEX IF NOT EXISTS idx_farm_diary_user_date ON farm_diary_entries(user_id, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_farm_expenses_user_crop_date ON farm_expenses(user_id, crop_id, incurred_on);
CREATE INDEX IF NOT EXISTS idx_farm_sales_user_crop_date ON farm_sales(user_id, crop_id, sold_on);
CREATE INDEX IF NOT EXISTS idx_market_prices_lookup ON market_prices(commodity, state, district, observed_on DESC);
CREATE INDEX IF NOT EXISTS idx_disease_reports_region_date ON disease_reports(state, district, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_regional_disease_alerts_region ON regional_disease_alerts(state, district, valid_until);
