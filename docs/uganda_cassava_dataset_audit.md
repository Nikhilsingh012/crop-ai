# Uganda cassava brown streak dataset: data quality and weather matching audit

Audit date: 25 October 2026. This was a read-only inspection of the four files already present in `data/crop_outcomes/source_files/uganda_cassava_brown_streak/`. No source file, application code, database, model, or risk rule was changed. CSV parsing used Python `csv.DictReader` with UTF-8 BOM handling and quote-aware parsing. Blank strings, `NA`, `N/A`, `NaN`, `nan`, `NULL`, `null`, `-`, and `--` were treated as missing. Dates were parsed as month/day/year first because unambiguous values such as `9/30/2011` (A) and `8/27/2008` (C) establish that ordering. All nonmissing A/C dates parsed successfully.

## Legend definitions (read from the workbook)

The workbook `LEGEND_CBSD_DATA.xlsx` has worksheets for A, B, and C. For Dataset A, `cbsd_foliar_presence` means foliar symptoms presence, with `0=NO` and `1=YES`; `cbsd_foliar_severity` is recorded on an ordinal 1?5 scale. For B/C, `cbsd_foliar_incidence` is defined as the ratio of infected plants to plants sampled. `cbsd_foliar_severity_mean` is the conditional mean of recorded foliar severity on 30 plants: 1 means no disease was observed in sampled plants; values 2?5 are conditional means of ordinal symptom scores greater than 1, on the 2?5 scale.

For C, `matched` is defined only as whether an overlapping record between A or B was identified (`YES`/`NO`). `data_origin` means the source survey record came from dataset A or B. `dbA_id` and `dbB_id` are the corresponding field IDs in those files. The legend does not specify a validation grade or independent validation procedure. It does not justify treating all rows as equally validated. Any additional validation qualification should be tied to the paper, not inferred from these fields alone.

## File inventory and schemas

| File | Parsed rows | Columns | Exact duplicate rows | SHA-256 |
|---|---:|---:|---:|---|
| DATASET_A.csv | 126,599 | 22 | 0 | `cb52ad29717331da97b4cbbd6ce10996ebd34cc0f6a99dfa21043e29585ef6b7` |
| DATASET_B.csv | 4,956 | 19 | 0 | `e150c0abb6410a6df69ce779b5280fcfc48a9d3ff76a5e60dcd639eaa7951bcd` |
| DATASET_C.csv | 7,627 | 28 | 1 | `9cf4d058e89896fd397091aa60f972e57e10dd69f1562e737cb63c0d98e4451c` |
| LEGEND_CBSD_DATA.xlsx | 3 sheets | ? | ? | `3f74cbead2aa32043a873d499fe112a9b8baed6b0d6b4145ce23488e1cdd0d25` |

Byte sizes: A 15,918,245; B 515,649; C 1,143,719; legend 11,531. The complete actual column lists are recorded in the JSON summary. The source directory also contains a prior `metadata.json` that says the dataset files could not be retrieved; it was left unchanged and is stale relative to the four files inspected here.

## Dates, coordinates, missingness

| File | Date precision and parsing | Coordinates |
|---|---|---|
| A | 121,439 of 126,599 plant rows have parsed dates; 5,160 are missing. Range 2004-07-27 to 2017-07-08. One date/year disagreement: `7/20/2016` with year `2015`. | All 126,599 rows have globally valid coordinates; 4,187 unique pairs. Latitude -0.9941667 to 3.74194; longitude 29.7349 to 34.75756. |
| B | There is no date or time column, only survey `year`; the legend defines year as survey year. | All 4,956 rows have globally valid coordinates; 4,941 unique pairs. Latitude -0.98744 to 3.81916; longitude 29.7349 to 34.78899. |
| C | 4,048 of 7,627 rows have parsed dates; 3,579 are missing. Range 2004-07-27 to 2017-07-08. All parsed date years agree with the `year` column. | All 7,627 rows have globally valid coordinates; 7,581 unique pairs. Latitude -0.9941667 to 3.81916; longitude 29.7349 to 34.78899. |

Every C record with a parsed date also has coordinates (4,048 rows), so these are the records eligible for a date-and-location join, subject to the duplicate/linkage caveats below. In A, dates repeat at plant level within field IDs; they are not 121,439 independent visits. The stored dates are calendar-day precision in the CSV; survey time is frequently missing (A 75,299 rows, C 5,917 rows), so the data do not support reliable within-day timing for every record. B?s year-only records cannot support daily weather alignment.

Key missing counts: A has 25,209 missing presence and 25,209 missing severity values. B has no missing incidence values and 2,850 missing severity means. C has no missing incidence, severity mean, matched, or data_origin values; it has 2,671 missing `dbB_id` and 3,407 missing `dbA_id`. Coordinates are complete across all files. Missing disease values were not recoded as no disease.

## Disease outcome distributions

**Dataset A (plant-level):** `cbsd_foliar_presence`: 21,309 YES (`1`), 80,081 NO (`0`), 25,209 missing. `cbsd_foliar_severity`: score 1: 80,081; 2: 14,127; 3: 6,818; 4: 346; 5: 18; missing: 25,209. These are the source?s ordinal symptom categories, not a percentage.

**Dataset B (field-level):** `cbsd_foliar_incidence` has 4,956 nonmissing values, range 0?100, mean 24.09, median 0, and 2,850 zeros. The workbook defines this as a ratio, but the observed B values extend to 100. The B scale therefore needs clarification before use as a fraction or percent. `cbsd_foliar_severity_mean` has 2,106 nonmissing values, range 2?4, median 2.1 and mean 2.285; 2,850 are missing. No missing values were imputed.

**Dataset C (field-level):** `cbsd_foliar_incidence` has 7,627 nonmissing values, range 0?1, mean 0.202, median 0, and 4,793 zeros. This observed scale is consistent with a fraction. `cbsd_foliar_severity_mean` has 7,627 values, range 1?4.5, median 1, mean 1.483; 4,793 equal 1 and 2,834 are greater than 1. The meanings remain those given in the legend: incidence ratio and conditional mean ordinal symptom score. Quantiles and full numeric summaries are included in JSON.

## Duplicates and documented link relationships

A has 4,220 unique field IDs: 4,219 IDs have 30 plant rows and one has 29. The plant rows are nested observations, so uncertainty and any train/evaluation split must be grouped by field ID.

C has one exact duplicate row. It also has five IDs appearing twice (`30218`, `31448`, `31706`, `31824`, `34064`); these are the same duplicated rows, each from `dbB`, marked `NO`, with the same `dbB_id` and field values. Do not count these repeated rows as distinct field visits without resolving duplication against the source/paper.

Using the documented ID fields, all 4,220 C records with a nonmissing `dbA_id` link to A. For the 3,273 linked fields where every A plant has a presence value, recalculating infected plants / sampled plants exactly reproduces C incidence (3,273/3,273). For 1,365 linked fields with qualifying A severity values and a C value, the conditional mean of plant scores greater than 1 reproduces C severity mean (1,365/1,365). These checks validate internal arithmetic only; they are not independent disease verification.

All 4,956 C rows with `dbB_id` link to B, but B/C incidence is inconsistent: 2,813 linked values are numerically equal as stored; 4,520 of the 4,956 satisfy C = B/100; 436 satisfy neither relation. These counts overlap because values such as zero are equal under both relationships. The B-to-C field ID linkage works, but it does not establish one universal scale conversion. Preserve original values and request source clarification before combining or rescaling.

C `data_origin`: dbA 4,220/7,627 (55.33%); dbB 3,407/7,627 (44.67%). C `matched`: YES 1,549/7,627 (20.31%); NO 6,078/7,627 (79.69%). By origin, dbA has 1,549 YES and 2,671 NO; dbB has 0 YES and 3,407 NO. The legend?s matched definition is about identification of overlap, not disease confirmation. Do not describe `NO` as unvalidated or `YES` as validated unless the paper independently supports that interpretation.

## Existing weather data and feasibility

The project?s weather pipeline documentation says it uses Open-Meteo?s Historical Forecast API; these data are historical forecast output, not observed weather or reanalysis. The latest stored run is `data/historical_weather/2022-01-01_2026-10-20_20261022T190549`, with 42,096 hourly rows, complete requested hourly coverage from 2022-01-01 through 2026-10-20, and no missing timestamps. It requested a point at 28.4744, 77.504 and the provider returned a grid point at 28.50615, 77.50853. Its variables include 2 m temperature, relative humidity, precipitation, soil temperature at several depths, soil moisture at several depths, and reference evapotranspiration; 0 cm soil temperature has 18.2% missingness in this run.

There is **no temporal overlap**: Uganda survey dates end in 2017, while stored weather starts in 2022. There is also **no spatial overlap**: cassava records are around latitude -0.99 to 3.82 and longitude 29.73 to 34.79, whereas the stored weather point is in the Delhi region near latitude 28.51, longitude 77.51. Existing weather cannot be matched to these observations. Historical weather matched to the wrong place or period would be invalid regardless of model method.

## Defensible future matching plan

1. Obtain a documented gridded historical weather product with Uganda coverage for the cassava observation dates, including product/version, temporal resolution, coordinate system, grid-cell spacing, units, and missingness. Do not treat forecast/reanalysis/gridded estimates as in situ observations.
2. Prefer Dataset C rows with parsed survey date, coordinates, nonduplicated field identity, and explicit provenance. For plant-level A, aggregate only at the documented field ID and preserve the 30-plant denominator/missingness; split and resample by field (and, if appropriate, location/time) to prevent leakage. Treat B-origin rows separately because only year is available and its incidence scale differs.
3. Extract weather at the matching grid cell for each field coordinate; retain point-to-cell distance and the source coordinates. Candidate covariates include daily precipitation totals, air temperature min/mean/max, relative humidity, and?if coverage/quality supports them?soil moisture and soil temperature. Leaf wetness is not present in the current weather files and should only be used if an appropriate product provides it.
4. Define exposures as pre-survey windows, for example 1?7, 8?14, and 15?30 days, as exploratory sensitivity windows rather than biological thresholds. The survey date is when symptoms were recorded, not necessarily when infection began. Use crop age where present and investigate missingness; do not include weather on/after the outcome date when evaluating advance warnings.
5. Select disease thresholds, lag periods, and alert lead time only from CBSD/cassava evidence and a prespecified analysis plan. This audit selects no biological threshold and does not infer disease outcome from weather.

## Limitations and next step

The exact dates and GPS coordinates make Dataset A and the date-populated subset of C promising for retrospective field-level associations once Uganda weather coverage is obtained. The present weather files cannot test the dataset. Dataset B is coarse in time, C has missing dates and duplicated dbB records, and B/C incidence scales are not consistently related. `matched` is not a validation flag by its documented definition. A/C internal consistency checks are useful but do not establish independent diagnostic confirmation or causal weather effects.

Next action: source a documented Uganda-covering historical weather dataset for 2004?2017, then first run a provenance-aware join on the date-bearing, nonduplicated A/C field records. Keep dbA- and dbB-origin outcomes separate until the incidence scale and record-validation questions are resolved. No weather merge was performed in this audit.
