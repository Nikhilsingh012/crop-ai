# Uganda cassava A/C linkage review

Read-only, deterministic review of original Dataset A and Dataset C rows. No weather API calls were made; source files and the 10-row weather pilot were not changed.

## Decision

All 14 disputed cases remain unresolved. Temporarily exclude the three A field IDs from field-visit weather matching because each contains conflicting actual date signatures. Send all 11 linked A/C coordinate discrepancies for manual review and exclude them from combined A/C field-visit matching pending coordinate adjudication. No coordinate or date was selected. A C-only weather extraction would retain C's own provenance and coordinates but would not reconcile its linked A record.

## A field IDs with conflicting signatures

Each field ID has 30 associated plant source rows. CSV and JSON include every A source row (line number, plant_id, actual date, coordinates, location labels, and disease labels) and the linked C row. C's date agreeing with one A signature does not adjudicate A: C is linked by ID and is not an independent correction record; matched=NO is not a validation status.

| A.id | Actual date/location signatures | A source rows | Linked C date/location | Decision |
|---|---|---:|---|---|
| 2015046 | `[{"date":"2015-07-18","latitude":0.47354,"longitude":33.51292},{"date":"2015-07-19","latitude":0.47354,"longitude":33.51292}]` | 30 | 7/18/2015 (0.47354, 33.51292; MAYUGE/BULONDO) | unresolved; exclude temporarily |

## Linked A/C coordinate discrepancies

Linkage uses documented `C.dbA_id = A.id`. All 11 dates are 2014-12-29. Deltas below are C minus A; Haversine distances are descriptive only and were not used to infer identity or choose a point. District labels differ in every case: C says KIBAALE, while A says MUBENDE for IDs 11625-11633 and KYEGEGWA for IDs 11635-11636. Village strings match, but that does not establish the correct coordinate. All C rows have data_origin=dbA and matched=NO. Existing documentation gives no correction history, coordinate precision rule, or preferred-source rule.

| A.id / C.id | Village | A coordinate (lat, lon) | C coordinate (lat, lon) | dLat | dLon | Approx distance | A district to C district |
|---|---|---|---|---:|---:|---:|---|
| 2015079 | `[{"date":"2015-07-20","latitude":0.54952,"longitude":32.63587},{"date":"2016-07-20","latitude":0.54952,"longitude":32.63587}]` | 30 | 7/20/2015 (0.54952, 32.63587; WAKISO/KASANA) | unresolved; exclude temporarily |

## Linked A/C coordinate discrepancies

Linkage uses documented `C.dbA_id = A.id`. All 11 dates are 2014-12-29. Deltas below are C minus A; Haversine distances are descriptive only and were not used to infer identity or choose a point. District labels differ in every case: C says KIBAALE, while A says MUBENDE for IDs 11625-11633 and KYEGEGWA for IDs 11635-11636. Village strings match, but that does not establish the correct coordinate. All C rows have data_origin=dbA and matched=NO. Existing documentation gives no correction history, coordinate precision rule, or preferred-source rule.

| A.id / C.id | Village | A coordinate (lat, lon) | C coordinate (lat, lon) | dLat | dLon | Approx distance | A district to C district |
|---|---|---|---|---:|---:|---:|---|
| 2015173 | `[{"date":"2015-07-16","latitude":0.91425,"longitude":33.15658},{"date":"2015-07-17","latitude":0.91425,"longitude":33.15658}]` | 30 | 7/17/2015 (0.91425, 33.15658; KAMULI/NAKIWUULO) | unresolved; exclude temporarily |

## Linked A/C coordinate discrepancies

Linkage uses documented `C.dbA_id = A.id`. All 11 dates are 2014-12-29. Deltas below are C minus A; Haversine distances are descriptive only and were not used to infer identity or choose a point. District labels differ in every case: C says KIBAALE, while A says MUBENDE for IDs 11625-11633 and KYEGEGWA for IDs 11635-11636. Village strings match, but that does not establish the correct coordinate. All C rows have data_origin=dbA and matched=NO. Existing documentation gives no correction history, coordinate precision rule, or preferred-source rule.

| A.id / C.id | Village | A coordinate (lat, lon) | C coordinate (lat, lon) | dLat | dLon | Approx distance | A district to C district |
|---|---|---|---|---:|---:|---:|---|
| 11625 / 11625 | KIBANGA | (0.54501, 31.42355) | (0.90835, 31.42355) | 0.363340 | 0.000000 | 40401.6 m | MUBENDE to KIBAALE |
| 11626 / 11626 | KYAHAKAMBA | (0.57402, 31.42813333) | (0.9567, 31.42813) | 0.382680 | -0.000003 | 42552.1 m | MUBENDE to KIBAALE |
| 11627 / 11627 | KITUUMA | (0.51702, 31.40605) | (0.8617, 31.40605) | 0.344680 | 0.000000 | 38326.7 m | MUBENDE to KIBAALE |
| 11628 / 11628 | KAKIMBALA | (0.46604, 31.20301667) | (0.776733, 31.20302) | 0.310693 | 0.000003 | 34547.5 m | MUBENDE to KIBAALE |
| 11629 / 11629 | KIGARAMA | (0.47014, 31.15155) | (0.783567, 31.15155) | 0.313427 | 0.000000 | 34851.5 m | MUBENDE to KIBAALE |
| 11630 / 11630 | BUKAMBA | (0.49372, 31.37695) | (0.822867, 31.37695) | 0.329147 | 0.000000 | 36599.5 m | MUBENDE to KIBAALE |
| 11631 / 11631 | KIHUMURA | (0.46543, 31.25166667) | (0.775717, 31.25002) | 0.310287 | -0.001647 | 34502.8 m | MUBENDE to KIBAALE |
| 11632 / 11632 | KIJANJA | (0.47549, 31.29398333) | (0.792483, 31.29398) | 0.316993 | -0.000003 | 35248.0 m | MUBENDE to KIBAALE |
| 11633 / 11633 | KITANDA | (0.47246, 31.36455) | (0.787433, 31.36455) | 0.314973 | 0.000000 | 35023.4 m | MUBENDE to KIBAALE |
| 11635 / 11635 | KIKANGE | (0.46847, 31.06151667) | (0.780783, 31.06135) | 0.312313 | -0.000167 | 34727.6 m | KYEGEGWA to KIBAALE |
| 11636 / 11636 | KYAMUGARAMA | (0.51325, 30.99586667) | (0.855417, 30.99587) | 0.342167 | 0.000003 | 38047.2 m | KYEGEGWA to KIBAALE |

Every case is unresolved and requires manual review before combined field-visit matching. Complete source-row evidence is in `data/crop_outcomes/processed/uganda_cassava_brown_streak/linkage_review/ac_linkage_review.csv` and `.json`.

## Reproducibility and constraints

Run `python scripts/uganda_ac_linkage_review.py` from the repository root to rebuild the deterministic CSV, JSON, and this report from the original A/C files. No matching by coordinate proximity or year is performed. No NASA POWER requests were made, and the pilot and source data were not modified.
