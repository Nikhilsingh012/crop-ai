# Crop Risk Intelligence

The crop-risk module extends the existing Flask/PostgreSQL application. It uses a deterministic risk engine as the authority and an optional Gemini call only to explain a result.

## Flow

1. A farmer or gardener adds a crop with coordinates and growth stage.
2. `services/weather/weather_service.py` returns normalized current and seven-day weather. Open-Meteo is the default provider; `DEMO_WEATHER_MODE=true` uses a clearly marked Greater Noida-style scenario. Results are cached by rounded coordinates.
3. JSON crop documents in `data/crop_knowledge/crops.json` supply available thresholds, stage context, actions, warning signs, and source status.
4. From `backend`, `python -m services.rag.ingest` validates the catalog and builds `data/crop_knowledge/index.json` with deterministic local embeddings. An optional model can be set through `RAG_EMBEDDING_MODEL_PATH` when it is already installed locally.
5. `services/agriculture/crop_risk_engine.py` calculates LOW, WATCH, MODERATE, HIGH, or SEVERE scores from rainfall, wet-day duration, humidity, temperature, and wind.
6. `services/crop_risk_service.py` stores weather snapshots and risk results and creates alerts only when a title/severity combination is new.
7. Gemini receives structured evidence only when `GEMINI_API_KEY` is configured. Invalid or unavailable responses leave the deterministic result unchanged.

When a location forecast contains a day at or above 64.5 mm, `/api/weather/risk` also returns a general rainfall exposure signal using the India Meteorological Department's heavy, very heavy, and extremely heavy rainfall ranges. The signal links to the source and explicitly states that forecast-day windows may differ from the IMD 24-hour station observation period. It is not an official IMD warning or a crop-specific risk score; the saved crop assessment remains unscored until that crop has reviewed threshold evidence.

## Tables

`user_crops`, `weather_snapshots`, and `crop_risks` are created by the existing `init_db()` startup migration. Legacy `crops`, `risk_predictions`, and `alerts` remain supported. New user-crop alerts use `alerts.user_crop_id`.

## APIs

- `POST /api/crops`: accepts the existing `field_id` payload or a location-aware payload with `crop_name`, `latitude`, and `longitude`.
- `GET /api/crops`: current user's location-aware crops.
- `GET /api/crops/<id>/risk`: latest stored risk for a user crop; legacy crops retain their existing behavior.
- `POST /api/crops/<id>/analyze`: force a fresh analysis.
- `GET /api/crops/<id>/weather`: normalized weather and forecast.
- `GET /api/crops/<id>/alerts`: active alerts.
- `GET /api/crop-catalog`: canonical registry, categories, aliases, and knowledge levels.

## Configuration and operation

Copy `.env.example` to `.env`, set `DATABASE_URL`, and optionally set `GEMINI_API_KEY`. Run `pip install -r requirements.txt`, build the RAG index, and start `python backend/main.py`. Set `DEMO_WEATHER_MODE=true` for an offline demonstration. A scheduler can call `run_crop_risk_analysis(crop_id)` periodically; the service already caches weather and deduplicates alerts.

To add a crop, add its canonical ID and aliases to `data/crops/crop_catalog.json`. Add a structured record only when there is crop-specific evidence, then rebuild the index. Thresholds should include traceable sources and be reviewed before production use. The current RAG corpus accepts structured crop JSON; PDF, CSV and text ingestion is not implemented.
# Crop catalog and evidence handling

`data/crops/crop_catalog.json` is the canonical crop registry shared by the Flask API, knowledge lookup, RAG filter and frontend search. It currently contains 188 unique crop IDs from the requested Indian crop list. Aliases resolve to canonical names while saved crop names remain readable.

Knowledge status is separate from crop recognition. All 188 catalog entries are currently `LIMITED`. The 15 legacy records in `data/crop_knowledge/crops.json` have unverified project thresholds without crop-specific references; those values are not used for scoring or retrieved as evidence. Recognized crops still receive weather and return `WATCH`, a null score, and an explicit limitation. Do not copy thresholds between crops or upgrade a record to `PARTIAL` or `FULL` without verifiable sources.

The generic engine contains deterministic rules for excessive rainfall, waterlogging, high humidity, heat stress, strong wind, and cold stress. These rules execute only when a source-backed crop record explicitly verifies its thresholds and supported types. No catalog crop currently meets that evidence requirement, so those numerical rules are dormant. Drought, frost, hail, storm, harvest rain, and stage-specific scoring are not implemented yet.

Rebuild the local index after changing knowledge records:

```powershell
Set-Location backend
python -m services.rag.ingest
```

The index carries `crop_id`, canonical name, aliases, region, stage, risk type, and source metadata. Queries first resolve aliases through the registry and then filter strictly on that ID; there is no cross-crop fallback. Add trusted PDF, CSV, JSON, text, or Markdown references under `data/crop_knowledge/sources/` with a `<filename>.metadata.json` sidecar, then rebuild the index. PDF text extraction requires selectable text; scanned PDFs need OCR first. URLs are syntax-checked during ingestion, but their claims still need human verification. The index deliberately excludes the 15 unverified legacy threshold records.

