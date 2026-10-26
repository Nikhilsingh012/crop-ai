# Migration policy

Files are applied in numeric filename order by `backend/db.py` and recorded in the `schema_migrations` table. The base application schema is created before numbered migrations run. Migrations are forward-only and must be safe to run once; startup serialization uses a PostgreSQL advisory transaction lock.

Migration 010 adds optional district, soil type, drainage condition, and irrigation availability fields to `user_crops` for location-aware crop-risk context. Existing records remain valid; missing context is reported as a limitation and is never silently inferred.

Before production rollout, take and verify a PostgreSQL backup, review the migration SQL, and deploy to a staging database first. Do not delete or edit an applied migration. Make a new numbered migration for corrections. Current migrations add profile/ownership fields and platform tables, then seed only official scheme names/URLs with unknown application status. No historical records are removed.

Migration `009_verified_pm_kisan_scheme_record.sql` adds the application procedure field and records the reviewed PM-KISAN criteria, documents, benefit and portal links. Other seeded schemes remain unverified. The scheme matcher requires fresh verified source data, labels self-reported screening as non-final, and does not persist eligibility answers. The official application status and deadline remain unknown; there are currently no verified upcoming deadlines.

Migrations `005_market_intelligence.sql` and `006_market_source_keys.sql` add grade-aware deduplication, stable source keys, and ingestion-run provenance. The importer uses the backend-only `DATA_GOV_IN_API_KEY` environment variable; schedule `python -m services.market_ingest` from `backend/` with an external scheduler after configuring that key. `MARKET_REFRESH_MAX_RECORDS` limits each manual/scheduled run.

Migration `007_finance_unit_conventions.sql` adds an explicit price denominator to sales records and owner/crop/season/date indexes. It preserves existing values and marks unit checks `NOT VALID` so previously stored legacy rows are not rewritten or discarded.

Finance calculations use decimal arithmetic and explicit conversions among kilograms, quintals, and tonnes. Break-even requires an expected saleable quantity; yield and price scenarios require recorded sales to supply a base price and are labeled as assumptions. Migration `007` was applied to the inspected development database without changing its three existing expense records or introducing sale records.

Migration `008_daily_farm_action_plans.sql` adds a nullable plan date and an idempotency key for generated daily checklist entries. Existing manually entered tasks keep `plan_date=NULL` and remain unchanged.

The daily checklist endpoint creates general inspection, soil-moisture-check, and diary prompts for each active saved crop. It can also add a limited-evidence reminder to refresh and review a forecast alert recorded for that farmer's crop within the last 24 hours; it does not turn the alert into treatment or input instructions. Verified, recently checked scheme deadlines within 30 days are returned only for central schemes or a matching saved farm state. Existing user-authored tasks remain visible, and completion/dismissal is owner-scoped. Crop-specific weather recommendations and broader verified-source planning remain incomplete.
