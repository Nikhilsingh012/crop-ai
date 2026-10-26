# Chickpea dry root rot supplementary workbook audit

## Scope and provenance

These files are a source-traceable extraction of selected tables from the publisher-linked Springer Nature XLSX workbook:

- Article: R. Sinha et al., “Low soil moisture predisposes field-grown chickpea plants to dry root rot disease: evidence from simulation modeling and correlation analysis,” *Scientific Reports* 11, 6568 (2021), DOI [10.1038/s41598-021-85928-6](https://doi.org/10.1038/s41598-021-85928-6).
- Publisher article and supplementary links: <https://www.nature.com/articles/s41598-021-85928-6>
- Workbook filename: `41598_2021_85928_MOESM2_ESM.xlsx`
- Workbook size at audit: 357,649 bytes.
- Publisher description: “Supplementary Information 2 (download XLSX)”; workbook sheet `Sheet1` calls it “Supplementary File S1: Raw data of all the measurements shown in the study”.
- The article is marked open access under CC BY 4.0. The publisher warns that some third-party material may have separate credit-line terms. The article page provides no workbook-specific licence statement.

The original workbook is preserved unchanged in `data/crop_outcomes/source_files/chickpea_dry_root_rot/`. Run `python backend/scripts/extract_chickpea_drr_supplement.py` from the repository root to reproduce these CSVs. Existing outputs are protected from accidental replacement; use `--overwrite` only when deliberately regenerating them.

## Extracted files

| File | Source | Rows | Record meaning |
| --- | --- | ---: | --- |
| `literature_records.csv` | `Supplementary Table S1 DataFile`, source rows 4–100 | 97 | Literature-derived disease/weather records used as source material for analyses; not 97 new CropAI field visits. |
| `farmer_field_entries.csv` | `Supplementary Figure S14`, source rows 4–13 containing `Field` labels | 6 | Field-level entries from farmer fields; each has five repeated readings in each of two unlabeled reading groups. These are not clearly dated disease-observation records. |
| `farmer_field_summary_measurements.csv` | `Supplementary Figure S14`, source rows 18–28 with summary values | 8 | Location/village-level summary rows containing disease incidence, soil moisture, and SEM values; these are aggregate summaries, not individual plants or plots. |

Each CSV includes `source_sheet` and the original one-based `source_excel_row`. Source columns are retained in their original order and with their original header text, including duplicate header names. Do not load the duplicated headings into a tool that silently renames or overwrites columns. In the literature CSV, the two `Variety` headers are source columns E and F. In the farmer-entry CSV, `Reading 1` through `Reading 5` each occur twice (source columns J:N and O:S).

The farmer-entry CSV also adds explicit audit annotations. `current_crop_identity_status` is always `ambiguous_current_crop`: the row-level crop field is actually named `Previous crop`. `previous_crop_flag` distinguishes a prior crop recorded as Chickpea, a prior crop recorded as something else, or a missing prior crop. This flag does not assign the current crop or turn a record into a chickpea disease outcome. Summary rows include `candidate_related_field_excel_rows`, which lists rows with the same village text, if any; it is only a traceable candidate association, not a join that claims the measurements belong to a particular field row.

## Field guide and units

### `literature_records.csv`

Columns are copied from source row 3: `State`, `Location`, `Taluka`, `Village`, `Variety`, `Variety`, `Seed treatment`, `Soil type`, `Rainfed/Irrigated`, `Soil number`, `DRR-DI`, `Year`; rainfall fields `RainF-Oct`, `RainF-Nov`, `RainF-Dec`, `RainF-Jan`, `RainF-Feb`, `RainF-OctNov`, `RainF-NovDec`, `RainF-DecJan`, `RainF-JanFeb`, `RainF-OctNovDec`, `RainF-NovDecJan`, `RainF-DecJanFeb`; minimum-temperature fields `MinT-Oct`, `MinT-Nov`, `MinT-Dec`, `MinT-Jan`, `MinT-Feb`, `MinT-OctNov`, `MinT-NovDec`, `MinT-DecJan`, `MinT-JanFeb`, `MinT-OctNovDec`, `MinT-NovDecJan`, `MinT-DecJanFeb`; and maximum-temperature fields `MaxT-Oct`, `MaxT-Nov`, `MaxT-Dec`, `MaxT-Jan`, `MaxT-Feb`, `MaxT-OctNov`, `MaxT-NovDec`, `MaxT-DecJan`, `MaxT-JanFeb`, `MaxT-OctNovDec`, `MaxT-NovDecJan`, `MaxT-DecJanFeb`.

`DRR-DI` is dry root rot disease incidence. The paper describes disease incidence as a percentage and the table’s weather values as monthly rainfall totals and monthly average temperatures, but the XLSX table itself gives no unit labels for `DRR-DI`, rainfall, or temperature. The extractor therefore preserves values and does not append units. The table contains a season/year label, not a day-level observation date. The paper describes chickpea and genotypes, but the source table also has incomplete and irregular crop/location metadata; do not infer a current crop from a variety-like value alone.

Missingness in this 97-row table: one missing `State`, one `Location`, one `DRR-DI`, and one `Year`; `Taluka`, `Village`, `Variety` and many weather/soil fields also have blanks. Blank cells stay blank. Exact full-row duplicate check on the 97 source records found zero duplicates. There is no publisher record ID; the Excel row is retained as source identity. The values are literature-derived and sometimes repeat weather summaries for multiple incidence values, so repeated weather values are not automatically duplicate observations.

### `farmer_field_entries.csv`

The source columns are `Location 1 Kadappa`, `N`, `E`, `Name of the farmer`, `Name of village`, `Mode of irrigation`, `Previous crop`, `Plant growth stage`, `Month of sowing`, followed by two same-named groups of `Reading 1`–`Reading 5`. The source does not label the measurement represented by either reading group, their units, nor the observation date. The `Month of sowing` cells are encoded as dates in October 2020; they are not disease observation dates. `N` and `E` contain coordinate-like values, but the table does not print a coordinate unit or a latitude/longitude header. Missing farmer names and any blank cells remain blank.

All six rows have ambiguous row-level current-crop identity because the crop column is `Previous crop`. Two entries list Groundnut as the previous crop; four list Chickpea. The article sheet title says representative chickpea fields, but that title does not resolve the row-level current crop or make the two Groundnut previous-crop entries chickpea observations.

Four of the six farmer-name cells are blank. All six `Month of sowing` cells serialize as `2020-10-01 00:00:00`; that encoded month is not a day-level disease observation date. The raw farmer-entry table has zero exact duplicate rows. The summary table has zero exact duplicate rows, and two summary rows have no matching village text in the field-entry section (the Sriganganagar rows). These checks do not establish that village text is a unique record key.

### `farmer_field_summary_measurements.csv`

Source headers: `Location`, `DI (%)`, `SMC (%)`, `DI SEM`, `SMC SEM`. `DI (%)` explicitly means disease incidence percent and `SMC (%)` explicitly means soil moisture content percent. `DI SEM` and `SMC SEM` are the source's standard-error-of-the-mean columns; no separate unit labels are printed, so they are not reinterpreted. This is a summary table by location/village, not plot-level weather/disease time series. It contains eight populated rows: two each under Kadapa, Anantapur, Kurnool, and Sriganganagar. The first three groups have matching village text in the field-entry section; Sriganganagar has no corresponding `Field` row there. The source does not say that village text alone is a unique field identifier.

## Workbook inspection inventory

The workbook has 22 sheets. Several have title rows above their tabular headers; raw data tables commonly use row 3. Some sheets are correlation matrices or figure data rather than independent observations. One sheet reports an Excel maximum-column dimension due to formatting, not 16,384 data fields.

| Sheet | Contents observed | Unit/header notes |
| --- | --- | --- |
| `Sheet1` | Supplementary File S1 title and author/affiliation text | No table. |
| `Supplementary Table S1 DataFile` | 97 literature-derived rows; location, variety/soil, `DRR-DI`, season/year, monthly and multi-month weather summaries | Duplicate `Variety`; no unit labels in this sheet. |
| `Figure 1Complete data file` | 97 rows of `DRR_DI` plus rainfall/minimum-temperature/maximum-temperature features | Last header `MaxT_DecJanFeb` is duplicated. |
| `Figure 1 Correlation coeffcient` | Correlation matrix for complete literature data | Matrix labels are variables; cells are coefficients, not observations. |
| `Figure 1 A1 Correlation File` | Genotype A1 analysis data | `DRR_DI` and monthly/multi-month weather features. |
| `Figure 1 A1 Correlation matrix` | A1 correlation matrix | Coefficients. |
| `Figure 1 JG11 Correlation File` | JG11 analysis data | Weather/DRR variables; sheet formatting inflates reported max column count. |
| `Figure 1JG11 Correlation matrix` | JG11 correlation matrix | Coefficients. |
| `Figure 1 RedS Correlation File` | Red-soil analysis data | Weather/DRR variables. |
| `Fig 1RedS Correlation Matrix` | Red-soil correlation matrix | Coefficients. |
| `Fig 1 BlackS Correlation File` | Black-soil analysis data | Weather/DRR variables. |
| `Fig 1 BlackS Correlation Matrix` | Black-soil correlation matrix | Coefficients. |
| `Fig 2 ANN Training File` | 96 training/testing data rows | `DRR_DI`, variety, soil number, weather summaries. |
| `Fig 2 Validation File` | 13 validation data rows | `DRR_DI`, variety, soil number, selected weather summaries. |
| `Supplementary Figure S7` | Soil-moisture values by treatment replicate and location-season | Header says soil moisture; no unit in the header. |
| `Supplementary Figure S8` | Monthly weather summaries by location-season | Rows include `MaxT`, `MinT`, `MaxH`, `MinH`; cells 12, 13, and 16 expand `MaxT`/`MinT`/`RainF`. No unit symbols are printed there. |
| `Supplementary Figure S9` | Disease severity index, disease incidence at 50% flowering, and disease incidence at podding by replicate | `Location 4_19-20` and `Location 5_19-20`; no percent sign/unit stated in the table headings. |
| `Supplementary Figure S10` | Total dry seed weight by replicate and trial location | Explicit `gm` (grams) in the source heading. |
| `Supplementary Figure S11` | Root length, lateral root number, root biomass by replicate | Explicit `Cm` and `Gm`; lateral root number is a count. |
| `Supplementary Figure S14` | Farmer-field entries plus a location summary table | Entry readings are unlabeled; summary explicitly labels DI and SMC percentages and SEM columns. |
| `Figure 4` | Disease incidence (%) under treatments across location-seasons and R1–R4 replicates | Controlled field-trial replicate results; location IDs do not give coordinates in this sheet. |
| `Figure 5` | Microsclerotia counts by genotype, treatment, and replicate | Counts; no date/location column in this sheet. |

The workbook provides no footnote defining the repeated reading groups in S14. The clear in-sheet unit notes include `DI (%)`, `SMC (%)`, total dry seed weight `(gm)`, root length `(Cm)`, and root biomass `(Gm)`. Other units are reported as unknown here rather than inferred from common conventions.

## Matching, duplicates, and use limits

These extracted data cannot be defensibly matched to the repository's current historical-weather series. The literature table contains seasons/years but not observation dates and covers earlier years. The farmer-field entries are around 14–15°N in Andhra Pradesh and have a sowing-month field, while the repository's weather point is around 28.5°N, 77.5°E for 2022–2026. Trial sheets use numbered locations and seasons, not matching coordinates. Do not assign daily weather exposure from monthly seasonal summaries, or fill missing dates/locations with guesses.

The farmer-field entries are candidates for manual review because the source has field labels, place names, coordinate-like values, and readings. Their reading definitions and current crop still need primary-source clarification. The literature records and trial summaries are useful as research context and aggregate evidence, but they are not clean, date-resolved individual observations suitable for joining to this weather point. No rows have been added to the project outcome template, database, or training data.
