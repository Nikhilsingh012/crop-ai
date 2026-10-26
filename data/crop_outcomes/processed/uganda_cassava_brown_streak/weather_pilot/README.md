# Uganda cassava disease / NASA POWER daily weather pilot

## Result

This is a 10-observation, exact-survey-date join of the existing Dataset C pilot inputs to the NASA POWER Daily API. The real API returned HTTP 200 for all ten point/date requests. All ten records have values for all three requested weather parameters and are marked `matched`; there were zero `missing weather`, `API failure`, or `invalid coordinates/date` records. No weather values were used to infer or alter disease observations. This pilot does not test weather-disease association or validate disease prediction.

| Check | Result |
|---|---:|
| Input observations | 10 |
| Output observations | 10 |
| Matched | 10 |
| Missing weather | 0 |
| API failure | 0 |
| Invalid coordinates/date | 0 |
| Missing T2M / PRECTOTCORR / RH2M | 0 / 0 / 0 |
| API requests | 10 |
| Exact-date alignment | Pass |
| Duplicate pilot observations | 0 |

## Source and interpretation

Provider: NASA Langley Research Center Prediction of Worldwide Energy Resources (POWER), Daily API point endpoint: `https://power.larc.nasa.gov/api/temporal/daily/point`.

Requested parameters and the units returned in every response:

- `T2M`: temperature at 2 meters, `C`.
- `PRECTOTCORR`: corrected precipitation, `mm/day`.
- `RH2M`: relative humidity at 2 meters, `%`.

The responses report `fill_value: -999.0`; the matcher treats this value, nulls, non-finite values, and other reported fill markers as missing (never as zero). No returned pilot value was missing. The response metadata reports `time_standard: LST`, sources `MERRA2` and `POWER`, and API version `v2.10.1`. Retrieval timestamps, HTTP status, request URL, parameter units, fill values, requested and returned coordinates/elevation, and source names are preserved in `request_metadata.json`; the original JSON response payloads are kept unmodified (apart from JSON serialization formatting) in `raw_cache/`.

NASA documents daily records back to 1981, daily UTC and LST, and native-source spatial resolution. Its meteorology methodology says MERRA-2 values are on a 0.5 degree latitude by 0.625 degree longitude grid and represent grid averages; the Daily API says point requests use source-native resolution. The API header identifies both MERRA2 and POWER, so this pilot records the provider's returned coordinates rather than assuming a field-scale cell size. Returned coordinates are rounded to three decimals in these responses and should not be interpreted as exact field coordinates. NASA?s public registry says POWER data have no use/access/download restrictions and asks users to cite POWER.

Official documentation:

- [NASA POWER Daily API: formats, dates, time standards, point requests](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)
- [NASA POWER API request tutorial: source-grid request guidance](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/)
- [NASA POWER meteorology methodology: MERRA-2 grid and grid averages](https://power.larc.nasa.gov/docs/methodology/meteorology/)
- [NASA POWER Registry: coverage and data use statement](https://registry.opendata.aws/nasa-power/)
- [NASA POWER relative-humidity methodology](https://power.larc.nasa.gov/docs/methodology/meteorology/relative-humidity/)

## Matching method and provenance

The matcher reads the actual header of `pilot_observations.csv` and resolves its `id`, `date`, `latitude`, and `longitude` columns. The selected input schema is recorded in `request_metadata.json`. It preserves every input column, including source IDs, `data_origin`, `matched`, and `dbA_id`/`dbB_id`, in `weather_matches.csv`.

For each unique coordinate, the runner groups the required dates into one inclusive request range. The current ten rows each have a unique coordinate and one observation date, so this run made ten single-day requests. It requests only the observation date, with `time-standard=LST`; it does not use a neighboring date or weather after the observation. A successful response is cached under `raw_cache/` using a SHA-256 key of the full request URL. Re-running the script reuses an existing valid cache entry rather than requesting that identical URL again. Cache JSON and its retrieval metadata sidecar are kept separate from `weather_matches.csv` and `quality_report.json`.

Each input row gets one status: `matched`, `missing weather`, `API failure`, or `invalid coordinates/date`. An absent requested date or missing requested variable is `missing weather`; HTTP, network, malformed JSON, API error, or malformed response is `API failure`. Failures do not drop input records. Invalid records are retained without a request. Duplicate input rows are retained and flagged; duplicate requests are grouped.

## Re-run

From the repository root:

```powershell
python scripts/uganda_power_weather_pilot.py
```

The script reads the existing `pilot_observations.csv`, reuses successful responses from `raw_cache/`, and rewrites `weather_matches.csv`, `quality_report.json`, and `request_metadata.json`. To use alternate input/output locations, pass `--input PATH --output-dir PATH`. Focused mocked tests:

```powershell
python -m pytest backend/tests/test_uganda_power_weather_pilot.py -q
```

## Exclusions and limitations

The pilot file contains ten date-bearing Dataset C records selected in the prior research step. The full Dataset C audit found 3,579 rows without dates; those were excluded and no year-only date was reconstructed. The previous audit also found duplicate IDs in Dataset C; the ten pilot IDs are unique. Dataset B and Dataset C incidence were not merged or rescaled. No disease labels or source observations were modified.

The response is a NASA gridded meteorological estimate, not an exact weather measurement at a cassava plot. The requested API date key exactly matches the recorded survey date and the response time standard is LST. No sub-day conversion is possible: the disease file records a calendar date, survey time is often missing, and its time zone is not specified. The survey date is not the infection date, and this join does not establish exposure timing or causality. No biological thresholds, lag rules, alert labels, model, or prediction claims are created here. A ten-row data-access pilot is not sufficient to assess spatial representativeness, weather-disease association, or predictive usefulness.

## Files and checksums

- `pilot_observations.csv` ? preserved input; SHA-256 `041c116ceafc11790634579b63405e5f2fe71716e45a0b678998c01459e0b967`.
- `weather_matches.csv` ? 10 joined rows; SHA-256 `586a1961f1368b91224f39153398ba0974fe3a637d343d48d2e50c478bb70b17`.
- `quality_report.json` ? status counts, validation checks, file hashes, and missingness.
- `request_metadata.json` ? per-request provenance and retrieval metadata.
- `raw_cache/*.json` ? ten original NASA POWER JSON responses; per-file hashes are listed in `quality_report.json`.
- `raw_cache/*.metadata.json` ? cache request and retrieval sidecars.

No weather aggregates beyond the exact daily matches were created.
