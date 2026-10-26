# Uganda cassava dataset: full weather-matching feasibility audit

Audit date: 2026-10-25. Read-only feasibility audit; **no full-dataset weather download was performed**.
The three CSVs were parsed independently with quote-aware `csv.DictReader`, UTF-8 BOM support, and common NA markers. Dates come only from actual date columns; no year-only dates were reconstructed.

## Dataset coverage

| Dataset | Observation unit | Rows | Valid dates | Valid coordinates | Date + coordinate eligible | Eligible IDs | Unique location/date pairs | Exact duplicate rows | Repeated ID groups |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | plant-level rows nested in field ID | 126,599 | 121,439 (95.92%) | 126,599 (100.00%) | 121,439 (95.92%) | 4,048 | 4,018 | 0 | 4,220 |
| B | field-level survey summary; year only | 4,956 | 0 (0.00%) | 4,956 (100.00%) | 0 (0.00%) | 0 | 0 | 0 | 0 |
| C | field-level aggregated record | 7,627 | 4,048 (53.07%) | 7,627 (100.00%) | 4,048 (53.07%) | 4,048 | 4,015 | 1 | 5 |

A rows are plants nested in field `id`; B and C are field-level summaries. Full actual column lists and per-column missing counts are in the JSON report.
B has no observation-date column, so all 4,956 records are ineligible for exact daily matching despite populated `year` and coordinates. Dataset A's year/date conflict count is 1; C's is 0.

## Year and geographic coverage

- A eligible plant rows by actual date year: `{"2004":18000,"2005":14280,"2006":9000,"2007":7590,"2008":5670,"2009":3150,"2010":12420,"2011":6000,"2013":18180,"2014":3840,"2015":11218,"2016":1,"2017":12090}`.
- B survey-year counts (not daily dates): `{"2008":474,"2009":390,"2010":698,"2011":752,"2012":545,"2013":1066,"2014":1031}`.
- C date-bearing rows by actual date year: `{"2004":600,"2005":476,"2006":300,"2007":253,"2008":189,"2009":105,"2010":414,"2011":200,"2013":606,"2014":128,"2015":374,"2017":403}`.
- Date ranges: A 2004-07-27 to 2017-07-08; C 2004-07-27 to 2017-07-08.

| Dataset (all valid-coordinate records) | Latitude range | Longitude range | Unique coordinates | Districts | Regions |
|---|---:|---:|---:|---:|---:|
| A | -0.9941667 to 3.74194 | 29.7349 to 34.75756 | 4,187 | 90 | 4 |
| B | -0.98744 to 3.81916 | 29.7349 to 34.78899 | 4,941 | 63 | 6 |
| C | -0.9941667 to 3.81916 | 29.7349 to 34.78899 | 7,581 | 95 | 4 |

C date-and-coordinate-eligible subset: 88 districts, 4 regions; latitude -0.9941667 to 3.74194, longitude 29.7349 to 34.75756.

## Disease-label availability and missingness

- A `cbsd_foliar_presence`: 101,390 nonmissing, 25,209 missing (0 NO: 80,081; 1 YES: 21,309); `cbsd_foliar_severity`: 101,390 nonmissing, 25,209 missing.
- B `cbsd_foliar_incidence`: 4,956 nonmissing, 0 missing; `cbsd_foliar_severity_mean`: 2,106 nonmissing, 2,850 missing.
- C `cbsd_foliar_incidence`: 7,627 nonmissing, 0 missing; `cbsd_foliar_severity_mean`: 7,627 nonmissing, 0 missing; `matched`: YES: 1,549, NO: 6,078; `data_origin`: dbA: 4,220, dbB: 3,407.
- `matched` records detected overlap under the legend, not independent disease validation. B/C incidence scales remain inconsistent and were not combined or rescaled.

## Duplicate records and linkage

A has 4,220 field IDs and 0 duplicated `(id, plant_id)` keys. Repeated A `id` values are expected plant rows within field groups; they are not duplicate disease rows. 3 A field IDs have conflicting eligible date/coordinate signatures: `[{"id":"2015173","eligible_signatures":[["2015-07-16",0.91425,33.15658],["2015-07-17",0.91425,33.15658]]},{"id":"2015046","eligible_signatures":[["2015-07-18",0.47354,33.51292],["2015-07-19",0.47354,33.51292]]},{"id":"2015079","eligible_signatures":[["2015-07-20",0.54952,32.63587],["2016-07-20",0.54952,32.63587]]}]`.
C has 1 exact duplicate row and 5 repeated ID groups covering 10 rows (IDs are listed in JSON). Using documented IDs, 4,220/4,220 C `dbA_id` references resolve to A and 4,956/4,956 C `dbB_id` references resolve to B. All 4,048 dated C records have `data_origin=dbA`.
Among date-bearing C records linked to A, 4,037 share exact date and coordinates; 11 share the date but have different coordinates. Examples: `[{"dbA_id":"11631","C_date":"2014-12-29","C_latitude":0.775717,"C_longitude":31.25002,"A_signatures":[["2014-12-29",0.46543,31.25166667]]},{"dbA_id":"11628","C_date":"2014-12-29","C_latitude":0.776733,"C_longitude":31.20302,"A_signatures":[["2014-12-29",0.46604,31.20301667]]},{"dbA_id":"11635","C_date":"2014-12-29","C_latitude":0.780783,"C_longitude":31.06135,"A_signatures":[["2014-12-29",0.46847,31.06151667]]}]`. Preserve both source values for review. Dataset rows are related only through ID fields; matching coordinates or years alone is not evidence to merge observations.

## Weather eligibility and estimated request volume

- A: 121,439 eligible plant rows, 4,048 eligible field IDs, 4,018 unique date/location keys after field grouping; 3 field IDs contain conflicting signatures.
- B: 0 date-specific eligible records; do not infer dates from year.
- C: 4,048 eligible field records, 4,015 unique exact location/date keys and 4,015 exact coordinate locations.
- A field signatures plus C records: 4,029 exact location/date keys across 4,026 coordinates. This deduplicates weather queries only; it does not merge disease outcomes.

| Strategy | Estimated calls | Daily values | Interpretation |
|---|---:|---:|---|
| Exact C coordinate/date requests | 4,015 | 4,015 | No overfetch, but too many synchronous calls without batching/pacing. |
| Min-to-max range per C coordinate | 4,015 | 4,015 | No call reduction for C because each eligible coordinate has only one date. |
| Min-to-max range per A/C coordinate | 4,026 | 4,394 | Fewer calls than exact keys, but includes intervening dates. |
| Source-grid grouping | Not safely countable from these files | Not estimated | Requires verified source-grid mapping; rounded response coordinates do not establish cell identity. |

Pilot-based storage proxy: mean raw one-day JSON response 1082 bytes; C exact-request raw payloads about 4,345,836 bytes (4.14 MiB). Pilot-sized matched CSV proxy is 1,446,351 bytes for C and 43,390,155 bytes if repeated across eligible A plant rows. Request-metadata proxy: 4,698,353 bytes. These estimates extrapolate only ten pilot rows and exclude cache sidecars and overfetch.

NASA advises using native source resolution and avoiding excessive synchronous requests. Its MERRA-2 meteorology documentation describes grid averages on a 0.5 degree by 0.625 degree grid. Pilot returned coordinates are rounded to three decimals; they do not establish a safe source-cell mapping for the full dataset. [Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/), [API request tutorial](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/), [MERRA-2 methodology](https://power.larc.nasa.gov/docs/methodology/meteorology/).

## Recommended batching and cache plan

1. Preserve distinct disease rows; derive weather request keys only from valid actual date and coordinates. Aggregate A only for request planning using field IDs, without discarding plant labels.
2. Before scaling, verify the source-cell mapping from authoritative NASA metadata. If valid, request each cell once for bounded contiguous date intervals; otherwise group only repeated exact locations.
3. Cache by endpoint, parameters, community, time standard, coordinate/cell key, and date range. Keep raw responses separate, checksum them, and use resumable checkpoints and explicit pacing.
4. Review the estimated 4,029 A/C unique location-date keys and output estimates before any full retrieval. **No full-dataset weather requests were made; stop here for review.**

## Exclusions and limitations

- A: 5,160 rows have missing dates; 0 nonmissing dates fail parsing; 0 rows lack valid global coordinates. The one date/year disagreement and three field-signature conflicts require preserving actual source dates.
- B: all 4,956 rows excluded from daily matching because no exact date is present; 4,956 do have valid coordinates and a year.
- C: 3,579 rows have missing dates; 0 nonmissing dates fail parsing; 0 rows lack valid global coordinates. No year was substituted.
- C duplicate IDs/rows, A plant clustering, eleven linked A/C coordinate discrepancies, B/C scale inconsistency, and lack of independent validation limit downstream use.
- Weather matches do not establish disease causality or prediction accuracy. No model or thresholds were changed.

## Reproducibility

Run `python scripts/uganda_dataset_feasibility_audit.py` from the repository root. It reads source CSVs and current pilot artifacts only, makes no network requests, and writes this report plus `data/crop_outcomes/processed/uganda_cassava_brown_streak/full_dataset_feasibility_audit.json`.
