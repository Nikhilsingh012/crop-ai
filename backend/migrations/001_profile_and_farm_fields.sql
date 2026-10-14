-- Additive profile and farm fields. Existing records and columns are preserved.
ALTER TABLE users ADD COLUMN IF NOT EXISTS state TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS district TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language TEXT NOT NULL DEFAULT 'en';
ALTER TABLE users ADD COLUMN IF NOT EXISTS location_consent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE scans ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE SET NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_preferred_language_check'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_preferred_language_check
            CHECK (preferred_language IN ('en', 'hi', 'hinglish'));
    END IF;
END $$;

ALTER TABLE farms ADD COLUMN IF NOT EXISTS area_amount NUMERIC(12, 3);
ALTER TABLE farms ADD COLUMN IF NOT EXISTS area_unit TEXT NOT NULL DEFAULT 'acre';
ALTER TABLE farms ADD COLUMN IF NOT EXISTS irrigation_method TEXT;
ALTER TABLE farms ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE fields ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE crops ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE user_locations ADD COLUMN IF NOT EXISTS consented_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'farms_area_unit_check'
          AND conrelid = 'farms'::regclass
    ) THEN
        ALTER TABLE farms ADD CONSTRAINT farms_area_unit_check
            CHECK (area_unit IN ('acre', 'hectare'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_state_district ON users(state, district);
CREATE INDEX IF NOT EXISTS idx_scans_user_created ON scans(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_user_created ON chat_messages(user_id, created_at DESC);
