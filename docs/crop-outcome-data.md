# Crop outcome data preparation

## Current state and scope

`data/crop_outcomes/template.csv` is a header-only import template. It contains **zero outcome observations**. The validator at `backend/services/crop_outcomes.py` reads a user-supplied CSV without altering it, checks its fields and provenance, and writes a coverage/validation report. It does not write records to PostgreSQL, publish data, match weather, or create labels. “Validated records ready for review” is not equivalent to an imported or training-ready record.

The current PostgreSQL schema has a `disease_reports` community-report table, but its fields are user/crop IDs, crop and symptom names, report date, state/district, optional growth stage, consent, verification status and expiry. It does not hold source-publication record IDs, measured severity or yield loss. The development database had zero `disease_reports` and zero `regional_disease_alerts` at inspection. Those app reports are not treated as historical ground truth. Existing `scans`, predictions, and CropAI risk outputs are also excluded as labels. No table or route was added.

The validator uses the existing `data/crops/crop_catalog.json` via `backend/services/crop_catalog.py`. Crop values must match the catalog's canonical display name; aliases are diagnosed but are not rewritten. Catalog entries not present in that file cannot pass until the project catalog is deliberately reviewed and extended.

## Template fields

The header row in `data/crop_outcomes/template.csv` includes:

- Provenance: `source_url` and/or `source_citation`, `publisher`, `original_record_id`.
- Observation: ISO `observation_date` (`YYYY-MM-DD`), canonical `crop`, state, district or location description, optional latitude/longitude and growth stage.
- Outcome: `outcome_type` (`disease_observation`, `crop_damage`, `yield_loss`), `hazard_or_disease`, `label_status` (`positive`, `negative`, `unknown`), `label_basis`, optional severity with its source-defined scale, or measured loss with its unit.
- Negative evidence: `negative_assessment_method` must describe an explicit assessment protocol for a negative label. “No report” or absence of a report is rejected as a negative observation.
- Quality: `verification_status` (`unverified`, `source_documented`, `independently_verified`, `expert_reviewed`), `uncertainty` (`low`, `medium`, `high`, `unknown`) and uncertainty notes.

Keep one source record per row and preserve its original ID, wording, units, and citation. Do not convert categories or units in the source CSV. The validator reports malformed dates, URLs, coordinates, crop names, status values, incomplete loss measures, missing provenance, duplicate publisher/record IDs, duplicate rows, and missing fields. It retains every input row and reports failures by CSV row number. A corrected or canonicalized copy should only be created as a separate, documented transformation after review.

## Validate and create the coverage report (Windows PowerShell)

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m backend.services.crop_outcomes `
  --input .\data\crop_outcomes\template.csv `
  --report .\data\crop_outcomes\coverage_report.json
```

The header-only template should report 0 rows, 0 validated observations, 0 records written to a database, and no validation failures. When genuine records are ready, retain the source file and pass its path with `--input`; the same command validates it and refreshes only the report JSON. A nonzero command exit means there are missing columns or row validation errors. The default report path is `data/crop_outcomes/coverage_report.json`.

## Finding genuine observations

Search official Indian agricultural research publication catalogues and institute repositories (ICAR and its crop-focused institutes, State Agricultural Universities, and their agricultural research station/KVK publications) for field trials, disease surveys, crop-cutting studies, and cultivar evaluations. Check the methods and tables in each paper or bulletin for the **place and period actually observed**, crop and stage, disease/damage definition, measurement method, sampling unit, and source record identifier. Prefer a publication's supplementary tables or a documented institutional dataset where individual observation rows and provenance are available. Record the exact citation/page/table and publisher; do not infer plot-level values from an abstract.

For government datasets, search the Government of India's open-data catalogue and agriculture ministry/directorate statistical releases, plus state agriculture department and crop-insurance releases. Confirm granularity and definitions before use. District/state annual production, yield, sown area, insurance claims, or disease-alert counts are aggregate statistics; they are **not** individual farm/date disease or damage observations. They can support aggregate analyses only at compatible time and geography. Weather services such as IMD are weather sources, not crop-outcome labels.

This implementation has not downloaded or verified any external crop-outcome dataset. It only provides the schema and validation route for records you obtain and document. Check publication/data reuse terms and retain enough citation metadata for every row.

## Keep outcome labels separate from weather

The historical weather output under `data/historical_weather/` is explicitly labeled historical forecast data, not observed weather/reanalysis. Do not join it to labels yet. District reports can represent several farms and dates, while the weather CSV represents one snapped provider grid and hourly timestamps. A district centroid or report publication date is not necessarily the affected field location or observation date. Matching them naïvely can assign the wrong exposure and create false precision. A future matching step needs source-specific event dates, location resolution, spatial/temporal buffers, the weather product's provenance, missingness handling, and an uncertainty record, then should preserve the unmatched originals and document every linkage.

No crop-damage labels have been fabricated, no ML model has been trained, and no crop-risk rules or thresholds were changed.

## Test fixtures

`backend/tests/test_crop_outcomes.py` contains synthetic values marked `TEST FIXTURE ONLY`. They test parsing and validation only and are not crop observations, ground truth, or training data.
