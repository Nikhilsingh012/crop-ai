ALTER TABLE market_prices ADD COLUMN IF NOT EXISTS source_record_key TEXT;

UPDATE market_prices SET source_record_key = md5(concat_ws('|',
    lower(provider), lower(commodity), COALESCE(lower(variety), ''), COALESCE(lower(grade), ''),
    COALESCE(lower(state), ''), COALESCE(lower(district), ''), COALESCE(lower(mandi), ''),
    observed_on::text, price_unit
)) WHERE source_record_key IS NULL;

ALTER TABLE market_prices ALTER COLUMN source_record_key SET NOT NULL;
DROP INDEX IF EXISTS uq_market_prices_observation;
CREATE UNIQUE INDEX IF NOT EXISTS uq_market_prices_source_key
ON market_prices(provider, source_record_key);
