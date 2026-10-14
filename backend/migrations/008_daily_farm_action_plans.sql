ALTER TABLE farm_tasks ADD COLUMN IF NOT EXISTS plan_date DATE;
ALTER TABLE farm_tasks ADD COLUMN IF NOT EXISTS generated_by TEXT NOT NULL DEFAULT 'farmer';
CREATE UNIQUE INDEX IF NOT EXISTS uq_farm_task_daily_plan
ON farm_tasks(user_id,crop_id,plan_date,title)
WHERE plan_date IS NOT NULL AND crop_id IS NOT NULL;
