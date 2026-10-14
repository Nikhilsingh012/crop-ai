ALTER TABLE market_prices ADD COLUMN IF NOT EXISTS grade TEXT;
ALTER TABLE market_prices ALTER COLUMN provider SET DEFAULT 'data.gov.in/AGMARKNET';

CREATE TABLE IF NOT EXISTS market_ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    source_url TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
    pages_fetched INTEGER NOT NULL DEFAULT 0,
    records_fetched INTEGER NOT NULL DEFAULT 0,
    records_upserted INTEGER NOT NULL DEFAULT 0,
    latest_observed_on DATE,
    error_message TEXT
);

-- The existing table was empty when this migration was prepared. Deduplicate
-- safely as well, so upgrading a database populated by an earlier importer works.
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY provider, lower(commodity), COALESCE(lower(variety), ''),
        COALESCE(lower(grade), ''), COALESCE(lower(state), ''), COALESCE(lower(district), ''),
        COALESCE(lower(mandi), ''), observed_on, price_unit
        ORDER BY fetched_at DESC, id DESC
    ) AS duplicate_rank
    FROM market_prices
)
DELETE FROM market_prices USING ranked
WHERE market_prices.id = ranked.id AND ranked.duplicate_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_market_prices_observation
ON market_prices (
    provider, lower(commodity), COALESCE(lower(variety), ''), COALESCE(lower(grade), ''),
    COALESCE(lower(state), ''), COALESCE(lower(district), ''), COALESCE(lower(mandi), ''),
    observed_on, price_unit
);
CREATE INDEX IF NOT EXISTS idx_market_ingestion_runs_recent
ON market_ingestion_runs(started_at DESC);
