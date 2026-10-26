ALTER TABLE user_crops ADD COLUMN IF NOT EXISTS district TEXT;
ALTER TABLE user_crops ADD COLUMN IF NOT EXISTS soil_type TEXT;
ALTER TABLE user_crops ADD COLUMN IF NOT EXISTS drainage_condition TEXT;
ALTER TABLE user_crops ADD COLUMN IF NOT EXISTS irrigation_availability TEXT;
