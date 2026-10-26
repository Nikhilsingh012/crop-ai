# Field survey template

Use `field_observations_template.csv` to record genuine crop and disease assessments. It contains only column headings; it has no sample or fabricated observations. Keep these field records separate from weather data and model predictions.

## How to fill it in

- Make one row for one crop, one target disease, and one assessment event. Give every row a unique `observation_id` that does not identify a farmer (for example, a project-generated code).
- Record the date and time when the assessment actually happened. Use `YYYY-MM-DD` for dates and `HH:MM` for local time. Record the timezone if known. Do not use sowing date or month as the disease assessment date.
- Enter crop variety, growth stage, disease name, method used to identify it, and the observer/source when known. For `disease_assessment_result`, use a documented result such as `present`, `not_detected_in_survey`, `not_assessed`, or `uncertain`. “Not detected” means an actual survey looked for the named disease; it does not prove the crop was disease-free.
- Leave unknown or unrecorded values blank. A blank is not zero, healthy, or disease-free. Explain important blanks in `missing_data_notes` (for example, “not recorded”, “farmer declined”, or “not applicable”) and describe uncertainty in `uncertainty_notes`. Use numeric zero only when zero was actually measured or counted.
- Record `plants_inspected` and `plants_affected` only when they were counted for the same assessment and sampling group. Calculate `disease_incidence_pct` only if both counts are known, inspected is greater than zero, affected is between zero and inspected inclusive, and both counts refer to that same group and event. The calculation is `100 × plants_affected ÷ plants_inspected`. Otherwise leave the percentage blank; do not convert missing counts to zero. State whether the percentage was calculated or directly measured in `incidence_measurement_method`.
- Preserve the severity value as recorded. Fill in its unit and scale description only when documented (including score range and what the endpoints mean, if available). Do not assume a common severity scale.
- Describe recent farm management and the period it covers when known. Do not turn a seasonal summary into daily exposure data.
- `identification_confirmation_status` can record `confirmed_expert`, `confirmed_lab`, `both`, `not_confirmed`, `pending`, or `unknown`; describe who/what confirmed it in `confirmation_details`. Do not mark a diagnosis confirmed based only on appearance unless that is the stated identification method.

## Location privacy

Collect precise farm GPS coordinates only with the farmer’s permission. Record `precise_location_consent` as `yes`, `no`, or `unknown` based on what was actually agreed. If permission was not granted or is unknown, leave precise coordinates blank; use a less precise location only if it is safe and appropriate, and describe its precision (farm, village, district, or approximate). Do not include farmer names, phone numbers, or other identifying details in the observer/source fields; an observer code is usually enough.

## Column guide

| Columns | Meaning |
| --- | --- |
| `observation_id` | Unique, non-identifying identifier for this assessment row. |
| `observation_date`, `observation_time`, `observation_timezone` | Actual assessment date/time and timezone, if known. |
| `crop_name`, `crop_variety`, `crop_growth_stage` | Crop identity and stage as observed or reported; leave unknown details blank. |
| `disease_name`, `disease_assessment_result`, `identification_method` | Target disease, assessment outcome, and how it was identified. Record a named disease assessment even when it was not detected. |
| `state`, `district`, `village`, `latitude`, `longitude`, `precise_location_consent`, `location_precision` | Place and coordinate information plus consent and location granularity. Coordinates are decimal degrees when recorded. |
| `plants_inspected`, `plants_affected` | Counts from the same assessment group, if actually counted. |
| `disease_incidence_pct`, `incidence_measurement_method` | Percentage and whether it was measured or calculated. The source record should support the value. |
| `severity_value`, `severity_unit`, `severity_scale_description` | Severity as measured, with documented unit and scale. These fields are not interchangeable with incidence. |
| `irrigation_method`, `recent_farm_management`, `management_period` | Irrigation and management context, including the period covered when known. |
| `observer_name_or_code`, `source_provenance` | Who collected the observation (prefer a code) and where the record came from, such as a survey form identifier. |
| `identification_confirmation_status`, `confirmation_details` | Whether and how an expert or laboratory confirmed the identification. |
| `missing_data_notes`, `uncertainty_notes` | Why important values are absent and any ambiguity or uncertainty. |

The existing outcome template and extracted research files are not modified. This template does not contain weather or model-output columns; link weather later only through a separately reviewed, defensible date and location match.
