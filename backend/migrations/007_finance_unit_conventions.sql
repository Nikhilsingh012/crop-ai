-- Make each recorded sale price's denominator explicit without rewriting prior amounts.
ALTER TABLE farm_sales ADD COLUMN IF NOT EXISTS price_unit TEXT;
UPDATE farm_sales SET price_unit = quantity_unit WHERE price_unit IS NULL;
ALTER TABLE farm_sales ALTER COLUMN price_unit SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='farm_sales_quantity_unit_supported' AND conrelid='farm_sales'::regclass) THEN
        ALTER TABLE farm_sales ADD CONSTRAINT farm_sales_quantity_unit_supported
            CHECK (quantity_unit IN ('kg','quintal','tonne')) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='farm_sales_price_unit_supported' AND conrelid='farm_sales'::regclass) THEN
        ALTER TABLE farm_sales ADD CONSTRAINT farm_sales_price_unit_supported
            CHECK (price_unit IN ('kg','quintal','tonne')) NOT VALID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_farm_expenses_owner_crop_season_date
ON farm_expenses(user_id,crop_id,season,incurred_on DESC);
CREATE INDEX IF NOT EXISTS idx_farm_sales_owner_crop_season_date
ON farm_sales(user_id,crop_id,season,sold_on DESC);
