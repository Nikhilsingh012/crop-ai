# Kheti Lens — Crop Risk and Farm Records

Kheti Lens is a Flask + PostgreSQL API and React/Vite web app for crop scans, weather-aware crop monitoring, farm records, and agriculture decision support. Risk advice is evidence-aware: where the repository has no verified crop-specific thresholds, it returns a watch state without a numeric score.

## Run locally

1. Copy `.env.example` to `.env` and set a unique `FLASK_SECRET_KEY` (at least 32 random characters). Keep `.env` private.
2. Start PostgreSQL and set `DATABASE_URL`. The Compose service exposes PostgreSQL on port `55432`.
3. In PowerShell:

```powershell
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Set-Location frontend
npm install
npm run build
Set-Location ..
python backend/main.py
```

Open <http://localhost:5000>. To run the full stack in containers, create `.env` with `FLASK_SECRET_KEY` and use `docker compose up --build`.

The API health route reports `database: unavailable` when PostgreSQL cannot be reached. The weather card supports browser location or a manual Indian town/district search, then requests an Open-Meteo forecast; saved farm risks and account records still require PostgreSQL. Browser geolocation requires localhost or HTTPS, and weather/location search requires access to Open-Meteo.

## Included features

- Email/password sign-in, owner-scoped farms/fields/crops, profile preferences, saved location, scan history, and admin-only aggregate views.
- Crop catalog and source-aware forecast risk. Crop records include a user-selected growth stage for care plans and risk context. Missing crop evidence is shown as a limitation rather than replaced with an unsupported score.
- Leaf scan workflow with local model status and optional Gemini Vision (`GEMINI_API_KEY`). Assistant responses are instructed not to invent current prices, deadlines, eligibility, or chemical doses.
- Persisted daily action checklists for active saved crops, with complete/dismiss controls; recent forecast alerts add only a refresh-and-review prompt, while freshly verified scheme deadlines within 30 days are shown for central or matching-state schemes.
- Farm diary plus owner-scoped accounting: expense/sale create, list, edit and delete; farm/crop/season/date filters; INR NUMERIC storage; kg/quintal/tonne conversions; per-crop/season totals; cost per acre when area is known; break-even only with expected saleable output; and clearly labeled yield/price scenarios based on recorded sales.
- Database-backed government scheme registry with search, state/level filters, source details/history, saved schemes and document checklists. PM-KISAN is matched deterministically against its official published criteria; the other seeded scheme records remain unverified and no application status/deadline is inferred.
- Admin-only allowlisted official source checks record content hashes and flag changes for human review; they do not auto-edit scheme records.
- Optional consent-based regional disease reports, displayed only as community signals after a minimum of five reports.
- Mandi Price Intelligence backed by an additive PostgreSQL schema, a validated data.gov.in/AGMARKNET importer, source dates, comparable-market analytics, and conservative forecast gating. Live ingestion requires a backend data.gov.in API key.
- Irrigation and harvest endpoints return insufficient-data states unless farmer-entered information supports them.

## Database migrations

The API applies numbered forward-only SQL files in `backend/migrations/` after the base schema, recording them in `schema_migrations`. They are additive and do not delete existing records. Before deploying a migration, back up PostgreSQL and review the SQL. To correct a deployed migration, add a new numbered migration; do not edit an already-applied migration.

Migration `007_finance_unit_conventions.sql` records a price denominator for each sale and adds non-destructive unit checks and accounting indexes. Migration `008_daily_farm_action_plans.sql` makes generated daily reminders persistent and idempotent. Supported sale quantity and price denominator units are `kg`, `quintal`, and `tonne`. The accounting API accepts `farm_id`, `crop_id`, `season`, `date_from`, `date_to`, `page`, and `per_page` filters. Updates and deletes use `PUT/PATCH/DELETE /api/farm/{expenses|sales}/<record_id>` and remain owner-scoped. The generated task endpoint is `GET /api/farm/actions/today`; completion and dismissal are owner-scoped `POST /api/farm/actions/<id>/{complete|dismiss}` routes.

An administrator can trigger `POST /api/admin/sources/check` with optional `{"source_keys":["pm-kisan"]}` and inspect `GET /api/admin/source-runs`. Checks fetch only an explicit official-domain allowlist, cap response size, and retain hashes/status rather than page contents. A changed page requires human review. Schedule `python -m services.retention` from `backend/` to remove opt-in disease reports after their 30-day expiry; run the retention job on a regular schedule in deployments.

## Tests and build

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
Set-Location ..\frontend
npm test
npm run build
```

The current test suite covers crop registry/risk behavior, weather handoff, and platform API authentication/claims. Database migrations and DB-backed workflows need a running PostgreSQL instance for end-to-end verification.

## Data and service limitations

- All 188 catalog crops currently have limited crop-specific threshold evidence. Add validated records with source URLs to `data/crop_knowledge/crops.json` and registry metadata before enabling numeric thresholds.
- Scheme rules are evaluated only when the record is verified and has been reviewed within 180 days. The PM-KISAN record was checked against the official portal and operational guidelines; answers in the checker are session-only and are not saved. The other four seeded records remain unverified. No upcoming verified deadline is currently recorded, and source changes still require human review before registry edits.
- The data.gov.in AGMARKNET importer stores official wholesale minimum, maximum, and modal prices with both arrival/observation date and backend fetch time. API-key generation is available to registered OGD users. If the provider times out, rejects credentials, or returns malformed data, existing stored observations remain available and the latest ingestion status reports the failure. e-NAM is linked as an official reference; no public automated API was verified.

### Mandi price refresh

Set these variables in the root `.env` (never in Vite/frontend variables):

```text
DATA_GOV_IN_API_KEY=your_data_gov_in_key
DATA_GOV_IN_MANDI_RESOURCE_ID=9ef84268-d588-465a-a308-a864a43d0070
DATA_GOV_IN_BASE_URL=https://api.data.gov.in/resource
```

The configured resource is the official OGD daily commodity/market resource. Its response is expected to contain a JSON `records` array with fields such as `state`, `district`, `market`, `commodity`, `variety`, `grade`, `arrival_date`, `min_price`, `max_price`, and `modal_price`. The backend validates the response and never turns provider failures into successful empty results.

Run a controlled manual refresh from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m services.market_ingest
```

An admin may also call `POST /api/markets/sync` while signed in. The endpoint is not available to ordinary farmers and does not expose credentials.

An external scheduler may run this command periodically. `MARKET_REFRESH_MAX_RECORDS` limits a run (default 10,000). The dashboard reports the actual newest observation date; it does not synthesize prices. The API returns no forecast until it has at least 56 consecutive calendar-day observations with valid modal prices for the selected commodity, variety, grade, and mandi. This conservative gate means many market histories will correctly remain unavailable.

- Gemini, external messaging, production voice transcription, and cloud deployment require service credentials/configuration. Browser speech input is device/browser dependent.
- Database-backed flows require PostgreSQL. The development server can serve the weather and public crop-catalog features without it, but cannot persist account activity.

## Project areas

- `backend/`: Flask app, routes, services, tests, and SQL migrations.
- `frontend/`: React/Vite app.
- `data/`: crop catalog and evidence-backed crop knowledge.
- `training/`, `notebooks/`: model training and analysis starter material.
- `docs/`: design and operational notes.
