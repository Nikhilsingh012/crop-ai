# Historical weather data pipeline

The read-only downloader at `backend/services/historical_weather.py` queries Open-Meteo's **Historical Forecast API**. Its output is historical forecast data, not observed weather and not reanalysis. It does not access PostgreSQL or alter app routes, risk rules, or crop records.

Each run creates a new uniquely named directory below `data/historical_weather/` (or the selected output directory). Existing run directories are never overwritten. Files are `raw_response.json`, `metadata.json`, `hourly.csv`, `daily_features.csv`, and `quality_report.json`. A field missing from the API is emitted as blank in CSV and counted in the report. Provider-grid coordinates are retained alongside requested coordinates in metadata.

## Windows PowerShell

From the repository root, first make a short API request:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m services.historical_weather `
  --latitude 28.4744 --longitude 77.5040 `
  --start-date 2022-01-01 --end-date 2022-01-03 `
  --timezone Asia/Kolkata `
  --endpoint https://historical-forecast-api.open-meteo.com/v1/forecast `
  --variables temperature_2m,relative_humidity_2m,precipitation,soil_temperature_0cm,soil_temperature_6cm,soil_temperature_18cm,soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm,et0_fao_evapotranspiration `
  --output-root ..\data\historical_weather
```

After checking the quality report, run the configured full range:

```powershell
..\.venv\Scripts\python.exe -m services.historical_weather `
  --latitude 28.4744 --longitude 77.5040 `
  --start-date 2022-01-01 --end-date 2026-10-20 `
  --timezone Asia/Kolkata `
  --endpoint https://historical-forecast-api.open-meteo.com/v1/forecast `
  --variables temperature_2m,relative_humidity_2m,precipitation,soil_temperature_0cm,soil_temperature_6cm,soil_temperature_18cm,soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm,et0_fao_evapotranspiration `
  --output-root ..\data\historical_weather
```

The command defaults already use those dates, location, endpoint, timezone, and variables. Dates, coordinates, endpoint, variable list, timeout, and output location are configurable. Use `--output-dir` only for a new, not-yet-existing path.

## Derived daily data and threshold evidence

Daily minimum and maximum air temperature and daily rainfall require their hourly fields; rainfall is null unless all 24 hourly values exist. Rolling rainfall sums are null unless the full 3 or 7 calendar-day window has complete daily rainfall. Night temperature summaries use local timestamps from 00:00–05:59 and 20:00–23:59; these are descriptive summaries, not a crop-specific definition of night stress.

Hot-day and dry-spell streaks are null unless configured. `--hot-day-threshold-c X` defines a hot day as daily maximum temperature strictly greater than X. `--dry-day-threshold-mm X` defines a dry day as complete daily rainfall less than or equal to X. These options accept caller-supplied thresholds; before using them for crop advisories, record a source supporting the crop, region, stage, variable, unit, threshold, comparator, and duration. The default does not invent either threshold. No crop-damage labels or ML predictions are produced.

The quality report includes HTTP status, requested and returned coverage, missing hourly timestamps within the returned span and across the full requested period, duplicate timestamps, missingness per requested variable, provider-returned coordinates, and output paths. A provider may return a shorter span without an internal gap, so check both counts and coverage.

## Tests

From repository root: `.\.venv\Scripts\python.exe -m pytest backend\tests\test_historical_weather.py -q`

