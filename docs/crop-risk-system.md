# Crop Risk Intelligence

The crop-risk module extends the existing Flask/PostgreSQL application. It uses a deterministic risk engine as the authority and an optional Gemini call only to explain a result.

## Flow

1. A farmer or gardener adds a crop to the growing list. A location-aware risk record is created only when forecast coordinates are selected; growth stage remains optional and is never inferred.
2. `services/weather/weather_service.py` returns normalized current, daily, and hourly forecast data. Open-Meteo is the default provider; `DEMO_WEATHER_MODE=true` uses a clearly marked Greater Noida-style scenario. Results are cached by rounded coordinates.
3. JSON crop documents in `data/crop_knowledge/crops.json` supply available thresholds, stage context, actions, warning signs, and source status.
4. From `backend`, `python -m services.rag.ingest` validates the catalog and builds `data/crop_knowledge/index.json` with deterministic local embeddings. An optional model can be set through `RAG_EMBEDDING_MODEL_PATH` when it is already installed locally.
5. `services/agriculture/crop_risk_engine.py` evaluates only rules whose source evidence is reviewed and marked verified in `data/crop_knowledge/risk_rule_registry.json`. The wheat IMD KALP rule checks daily Tmax over five forecast dates. The potato ICAR-CPRI rule flags daily minimum temperature at or above 20Â°C across the next two consecutive future calendar days as outside the stated preferred tuberization condition. All three are deterministic weather indicators without severity or numerical damage probabilities. The rice indicator flags any of the next 48 consecutive complete hourly 2 m temperature forecasts strictly above 35°C during flowering/anthesis; this 48-hour window is an app reporting horizon, not a source-validated damaging duration. Temperature is air temperature rather than crop tissue temperature. The nine prior provisional records remain unchanged and excluded.
6. `services/crop_risk_service.py` stores weather snapshots and risk results and creates alerts only when a title/severity combination is new.
7. Gemini receives structured evidence only when `GEMINI_API_KEY` is configured. Invalid or unavailable responses leave the deterministic result unchanged.

The application reassesses location-aware saved crops when a signed-in session loads and when the farmer selects **Check saved crop alerts**. A legacy growing-list crop without its own saved forecast location cannot be joined to a location-aware assessment by name; the risk page says this explicitly. Browser coordinates alone do not establish country or state. Missing stage or region data is retained as missing and causes stage/region-limited rules to report unavailable. Farmers can update the stage on each saved risk record from the assessment card; this updates that location-aware crop and reruns its assessment. Crop-specific forecast alerts are stored in-app and deduplicated by saved crop and event title (the rule and forecast date are part of the title). No email or SMS notifications are sent.

When a location forecast contains a day at or above 64.5 mm, `/api/weather/risk` also returns a general rainfall exposure signal using the India Meteorological Department's heavy, very heavy, and extremely heavy rainfall ranges. The signal links to the source and explicitly states that forecast-day windows may differ from the IMD 24-hour station observation period. It is not an official IMD warning or a crop-specific risk score; the saved crop assessment remains unscored until that crop has reviewed threshold evidence.

## Tables

`user_crops`, `weather_snapshots`, and `crop_risks` are created by the existing `init_db()` startup migration. Legacy `crops`, `risk_predictions`, and `alerts` remain supported. New user-crop alerts use `alerts.user_crop_id`.

## APIs

- `POST /api/crops`: accepts the existing `field_id` payload or a location-aware payload with `crop_name`, `latitude`, and `longitude`.
- `GET /api/crops`: current user's location-aware crops.
- `GET /api/crops/<id>/risk`: latest stored risk for a user crop; legacy crops retain their existing behavior.
- `POST /api/crops/<id>/analyze`: force a fresh analysis.
- `PATCH /api/crops/<id>/context`: update the saved crop assessment's growth stage, state, or country.
- `GET /api/crops/<id>/weather`: normalized weather and forecast.
- `GET /api/crops/<id>/alerts`: active alerts.
- `GET /api/crop-catalog`: canonical registry, categories, aliases, and knowledge levels.
- `GET /api/crop-risk-coverage?crop=<name>&state=<state>&stage=<stage>`: verified rule and coverage inventory, optionally filtered to a crop and context.

## Configuration and operation

Copy `.env.example` to `.env`, set `DATABASE_URL`, and optionally set `GEMINI_API_KEY`. Run `pip install -r requirements.txt`, build the RAG index, and start `python backend/main.py`. Set `DEMO_WEATHER_MODE=true` for an offline demonstration. A scheduler can call `run_crop_risk_analysis(crop_id)` periodically; the service already caches weather and deduplicates alerts.

To add a crop, add its canonical ID and aliases to `data/crops/crop_catalog.json`. Add a risk rule only after verifying crop-, stage-, and region-relevant evidence, and configure a deterministic evaluator supported by the weather provider. The coverage inventory shows missing hazard families and unsupported rule requirements. From `backend/`, run `python -m services.agriculture.crop_risk_coverage` to print the report. No stage is inferred by the risk engine.
# Crop catalog and evidence handling

`data/crops/crop_catalog.json` is the canonical crop registry shared by the Flask API, knowledge lookup, RAG filter and frontend search. It currently contains 188 unique crop IDs. Aliases resolve to canonical names while saved crop names remain readable.

Knowledge status is separate from crop recognition. The legacy records in `data/crop_knowledge/crops.json` include unverified project thresholds; those values are not used for scoring. A recognized crop with no applicable verified rule returns unavailable with a null score. Do not copy thresholds between crops or upgrade a record to `PARTIAL` or `FULL` without verifiable sources.

## Hazard evaluator support

| Hazard family | Inputs and horizon | Current status and limitation |
| --- | --- | --- |
| Heat stress | Wheat at grain filling: daily 2 m Tmax in Â°C, five consecutive daily forecast records, strict >30Â°C trigger from IMD KALP. Existing hourly evaluator supports up to 48 future samples. | Wheat at grain filling and rice at flowering/anthesis have deterministic heat indicators, plus potato tuberization preferred night-temperature condition. Outputs have no probability or damage score. Nine older crop-specific heat records remain provisional. |
| Excess rainfall | Hourly precipitation is available, but there is no verified crop-specific accumulation evaluator/rule. | Unavailable for crop-risk scoring. The separate general rainfall signal is not a crop rule. |
| Cold/frost | Hourly and daily minimum temperatures are available, but no verified crop-specific frost threshold/evaluator is registered. | Unavailable; do not infer frost injury from unreviewed generic thresholds. |
| Dry spell | The forecast provides precipitation, not a sufficiently long observed precipitation history or soil moisture. | Unavailable; no drought inference from heat or short forecast rainfall. |
| Disease-favourable weather | Hourly humidity, temperature, and precipitation are available; leaf wetness and complete disease-specific forecast criteria are absent. | Unavailable; weather exposure cannot be called infection or diagnosis. The rice heat rule is not a disease rule. |
| Severe weather | Hourly wind and precipitation are available; authoritative warning feeds, gust support in the risk summary, and verified crop rules are absent. | Unavailable as a crop hazard assessment; generic thresholds are not substituted for official warnings. |

The coverage endpoint reports verified executable rules separately from provisional records, incomplete evidence, mismatched citations, unsupported evaluators, and missing weather inputs. The rule-specific source audit and uncovered-hazard candidates are in `data/crop_knowledge/risk_rule_evidence.md`. Provider capability is not proof that a crop hazard was assessed: each assessment still reports `unavailable` or `insufficient_data` until a matching verified rule has adequate observations. No catalog-wide claim of risk coverage should be inferred from crop recognition. The location weather panel displays at most five daily rows; individual verified rules retain their own source-defined or explicitly documented evaluator windows.

Saved-crop analysis at `POST /api/crops/<id>/analyze` creates an in-app WATCH alert for each triggered deterministic rule. Alerts include the crop, forecast date/time and timezone, observed condition, threshold, and source URL. The risk page's **Check saved crop alerts** action refreshes current assessments for all saved crops. Repeated runs for the same rule and forecast date are deduplicated. These alerts describe forecast exposure, not confirmed disease or crop damage; unavailable rules do not generate low-risk alerts. Email and other external notification channels are not enabled.

Rebuild the local index after changing knowledge records:

```powershell
Set-Location backend
python -m services.rag.ingest
```

The index carries `crop_id`, canonical name, aliases, region, stage, risk type, and source metadata. Queries first resolve aliases through the registry and then filter strictly on that ID; there is no cross-crop fallback. Add trusted PDF, CSV, JSON, text, or Markdown references under `data/crop_knowledge/sources/` with a `<filename>.metadata.json` sidecar, then rebuild the index. PDF text extraction requires selectable text; scanned PDFs need OCR first. URLs are syntax-checked during ingestion, but their claims still need human verification. The index deliberately excludes the 15 unverified legacy threshold records.

## Current executable coverage and score policy (2026-10-25)

The verified executable registry currently supports only three crop-specific weather indicators: rice at flowering/anthesis, wheat at grain filling, and potato at tuberization. All three are in the heat-stress family. `corn` resolves to maize, but maize has no verified rule. Spinach has a provisional, excluded heat candidate; carrot has no rule. The five other hazard families remain unsupported for crop-specific assessment. Each hazard is evaluated independently, so a missing rule in one family does not suppress a separate applicable verified rule.

Verified deterministic indicators now include a per-rule weather exposure index: `round_half_up(100 × observations meeting that rule condition / valid observations in that rule's complete assessment window)`. The index boundaries are 0 when none of the valid observations meet the condition and 100 when all do. Intermediate values are the rounded observation share. Each result includes the numerator, denominator, and observation unit. This is weather exposure, not disease probability or crop-damage severity; no LOW/MODERATE/HIGH bands are assigned.

The index is per rule, not a crop-wide score. Do not add, average, or take a maximum across hazards: there is no common calibrated severity scale, and these rules use different sample units and windows. The top-level `risk_score` remains null for the rice, wheat, and potato deterministic indicators. Their overall status remains partial because the other hazard families lack verified rules. A zero rule-window index means only that no observation crossed that rule's condition; it does not mean overall low risk.

A demo-mode weather payload is simulated and must not be treated as a crop-specific forecast assessment. It is now withheld from rule evaluation and explicitly identified in missing inputs. The API shape and database schema remain unchanged.

The additional maize, cotton, soybean, tomato, groundnut, and potato disease sources reviewed in the risk-rule evidence log do not specify a complete, compatible, validated rule for the current provider and saved crop context. No new executable rule or threshold was added. Existing rule thresholds and recommendation text were not changed.

## Estimated weather-risk model (additive, 2026-10-26)

Verified rule findings remain the only source-backed hazard conclusions. To stop crops without a verified rule from showing only "unavailable", each assessment now also returns a separate `model_assessment` object. It never changes the top-level verified `status`, `risk_score`, `overall_risk`, or alert semantics, and the UI keeps the two layers visually distinct.

The model is a deterministic agronomic suitability heuristic, not a machine-learning probability and not a probability of crop loss. It combines the local forecast with crop tolerances and sensitivities:

- forecast daily maximum/minimum temperature and rainfall over the assessment window, plus current/hourly humidity and wind;
- optimal temperature range, heat and cold thresholds, heavy-rain reference, weekly water need, humidity and wind thresholds;
- waterlogging and drought sensitivity plus the crop's sensitive hazards;
- growth-stage multipliers for germination, seedling, vegetative, tuber initiation, flowering, fruiting, grain filling, maturity and harvest.

Scores are `0-100` and map to LOW `0-29` (green), MODERATE `30-59` (orange, watch), and HIGH `60-100` (red, alert). `safe_percent` is the complement of the risk percentage. The result carries the model name/version, method, `is_probability: false`, contributor factors with evidence, confidence, recommendations, profile provenance, inputs, and limitations. Demo forecasts, missing weather, and unusable observations return `insufficient_data` with no percentage.

Profile provenance is reported as:

- `crop_knowledge`: the crop has a detailed profile in `data/crop_knowledge/crops.json`;
- `crop_specific_tuning`: the crop is tuned in `data/crop_knowledge/weather_risk_model.json`;
- `category_default`: the crop uses its catalog category profile (cereal, pulse, oilseed, vegetable, fruit, plantation, spice, fodder, commercial) or the generic fallback.

This gives all 188 catalog crops a bounded estimate, while crops with better agronomic knowledge receive more specific thresholds. Implementation lives in `backend/services/agriculture/weather_risk_model.py`; configuration lives in `data/crop_knowledge/weather_risk_model.json`. Tests cover every catalog crop, profile provenance, all three bands, the safe complement, missing stage, demo/missing weather, stale forecasts, and the guarantee that verified fields stay unchanged.
