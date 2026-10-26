# Protocol research: farmer-field survey in Supplementary Figure S14

## Sources checked

1. **Main article (publisher):** Sinha et al., “Low soil moisture predisposes field-grown chickpea plants to dry root rot disease: evidence from simulation modeling and correlation analysis,” *Scientific Reports* 11, 6568 (2021), DOI [10.1038/s41598-021-85928-6](https://doi.org/10.1038/s41598-021-85928-6). Article sections checked: “Field experiments for assessing DRR incidence and associated factors,” “Field data analyses,” and relevant Results/figure captions. Publisher page: <https://www.nature.com/articles/s41598-021-85928-6>.
2. **Official Supplementary Information 1 (publisher PDF):** 37-page file linked from the article. S14 caption is on PDF page 20 (printed page numbering is not shown in the extracted text). Direct publisher URL: <https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41598-021-85928-6/MediaObjects/41598_2021_85928_MOESM1_ESM.pdf>. Also checked the S13 caption on PDF page 19 because S14 explicitly refers to its DI method, and S7 on PDF page 12 for a related but separate experimental protocol.
3. **Cited original method source:** Sinha et al. (2019), “Impact of drought stress on simultaneously occurring pathogen infection in field-grown chickpea,” *Scientific Reports* 9, 5577, DOI [10.1038/s41598-019-41463-z](https://doi.org/10.1038/s41598-019-41463-z). Publisher page: <https://www.nature.com/articles/s41598-019-41463-z>. The 2021 article cites this as reference 5 in its main text and points to it for the field-trial DI method. Its Materials and methods sections “Soil moisture content” and “Disease identification and calculation of incidence and index” were checked. This paper describes a different controlled field-trial setup; its more detailed meter depth and frequency should not be silently transferred to S14's farmer survey.
4. **Local source workbook:** `data/crop_outcomes/source_files/chickpea_dry_root_rot/41598_2021_85928_MOESM2_ESM.xlsx`, sheet `Supplementary Figure S14`, compared directly with `farmer_field_entries.csv` and `farmer_field_summary_measurements.csv`.

The browser-accessible publisher text for the official PDF exposed the full S14 caption and relevant supplementary methods. The PDF page screenshot itself could not be fetched by the browser tool (cache miss), so this audit relies on the publisher's parsed PDF text and the actual XLSX cells rather than a visual reading of the figure artwork.

## Confirmed from the sources

### What the two groups of `Reading 1`–`Reading 5` mean

- The XLSX has two groups with the same headers (`Reading 1` through `Reading 5`) and no group labels or units in the cells above them. The workbook alone does **not** label the first group.
- S14's publisher caption says soil moisture was measured with a **Lutron PMS-714** meter, and that soil-moisture data are an average of five locations within the selected region (Supplementary PDF, S14, p. 20). The second group of five XLSX values matches that description: for each of the six field rows, the arithmetic mean and sample SEM of the second group reproduce the corresponding summary-table `SMC (%)` and `SMC SEM` values (to spreadsheet precision). The five values are therefore the SMC readings, supported by both the caption and exact row-by-row numerical agreement. This identifies the second group; it does not provide a label for the first.
- **The first group remains unidentified.** It is not safe to call it DI, soil moisture, another environmental measure, or five replicate disease assessments: the publisher text and workbook headers do not explain it, and its values do not reproduce the table's DI or DI SEM by a simple mean/SEM calculation. Preserve those cells as unlabeled readings unless the authors or another primary record clarify them.

### SMC method and summary

- The S14 caption explicitly states soil moisture content is in percent, measured with the Lutron PMS-714, and that the summary soil-moisture data average five locations within the selected region (Supplementary PDF, S14, p. 20).
- In all six source rows, the second five-reading group calculates to the summary `SMC (%)`; its sample SEM likewise calculates to the summary `SMC SEM`. This was checked against the workbook values, not assumed from the duplicate header.
- S14 does **not** state measurement depth, how many meter insertions were made at each location, or the calendar date/time of each reading. Although the separate 2019 Sinha et al. controlled field experiment measured soil moisture every other day at 15 cm using the same model meter and averaged block replicates (main article, Materials and methods, “Soil moisture content”), those details are for its own RCBD trial and are not evidence of the S14 farmer-survey protocol.

### Disease incidence and SEM

- S14 says four random plots of three square metres were selected and disease incidence was calculated using the method in S13 (Supplementary PDF, S14, p. 20). S13 explicitly defines `% Disease Incidence = (number of infected plants / total number of plants) × 100` (Supplementary PDF, S13, p. 19). Thus DI is a percentage based on infected plants divided by all plants counted, rather than a disease-severity score.
- The S14 caption describes the plotted DI as an average for four selected field plots/locations and says the error bar represents SEM (Supplementary PDF, S14, p. 20). The XLSX summary labels its corresponding columns `DI (%)` and `DI SEM`.
- The workbook does not expose the four underlying plot-level infected/total counts or DI values, so the reported DI or its SEM cannot be recalculated from the extracted S14 rows. The caption identifies SEM as the error-bar statistic, but does not print its calculation formula or all replicate-level inputs. No DI replicate values are hidden in the extracted five-reading groups by a simple match to the summary.
- For SMC, the summary's `SMC SEM` can be reproduced from the five SMC readings in the XLSX. The S14 caption does not spell out the SEM formula; the agreement is a direct numerical check, while interpreting it as the conventional sample SEM is an inference from that calculation.

### Crop identity, phenology, dates, and locations

- **Current crop is supported independently of `Previous crop`:** the S14 caption says the survey assessed dry root rot in chickpea cultivation and that **JG 11 chickpea was cultivated** in the listed Kadapa, Anantapur, and Kurnool locations in 2019–20 (Supplementary PDF, S14, p. 20). This supports chickpea/JG 11 identity for the six listed field entries. The XLSX `Previous crop` column is a separate historical-crop field and must not be mistaken for current crop. Two entries say the previous crop was Groundnut; four say Chickpea.
- The S14 caption says observations were taken during **flowering/pod-filling stage**. It does not provide six specific observation dates or a date for any one field.
- Each XLSX field row has `Month of sowing` encoded as `2020-10-01 00:00:00`. This is sowing-month information, not a disease-assessment date. It is also apparently inconsistent with the caption's 2019–20 trial season; the workbook's encoded value cannot resolve that mismatch. No calendar observation dates should be derived from the crop stage or sowing-month cell.
- The six workbook field rows are two each for Kadapa (sheet spelling `Kadappa`), Anantapur, and Kurnool. The S14 caption lists these districts and villages. The caption says JG 11 was cultivated under rain-fed conditions, while two of the six XLSX rows (`Chinna Chepali` and `Ragulapadu`) have `Mode of irrigation = Irrigated`. This source inconsistency should remain visible rather than being normalized away.
- The XLSX summary has eight village rows, including two Sriganganagar rows without matching farmer-field entries in the raw section. The S14 caption acknowledges a Sriganganagar research-station field, but does not identify those two summary rows as individual farmer fields. Do not manufacture corresponding raw observations.

## Unresolved questions

1. What does the first group of five `Reading` values measure, and what are its units and sampling procedure?
2. Why are sowing-month cells encoded as October 2020 when the S14 caption identifies the survey as 2019–20?
3. Why do two XLSX entries say “Irrigated” when the S14 caption says the named JG 11 locations were rain-fed?
4. What are the individual plot DI numerators/denominators and plot-level DI values used to calculate each village DI and `DI SEM`?
5. Does the SMC summary SEM use exactly the five readings shown in the second group for each field? Numeric mean and SEM matches support this, but the caption only explicitly says the mean is based on five locations.
6. Are Sriganganagar's summary rows associated with separate survey fields omitted from the raw-entry block, or another source record? The current workbook does not say.

## Cautious inferences (not additional source facts)

- The second reading group is SMC because all six five-value averages and SEMs reproduce the SMC summary values, and the S14 caption independently says SMC is averaged across five locations. This is a strong, auditable inference from the published values, although the spreadsheet column headers are still unlabeled.
- The first reading group could be a different field measurement, but there is not enough evidence to assign it a name or unit.
- S14's four-plot DI SEM likely summarizes variation among those four plot-level DI measurements, consistent with the caption's average and SEM wording. Since the underlying plot readings are absent, the precise replicate structure and calculation cannot be independently checked.
- The fact that the caption names JG 11 as the crop variety supports current-crop identity for the six entries, but the rain-fed statement conflicts with two row-level irrigation labels. This does not establish that every other workbook summary row (notably Sriganganagar) corresponds to a raw field entry.

## Suitability for CropAI

These findings clarify more metadata than the XLSX alone: the six described entries are chickpea JG 11, the second reading group is SMC (%), and DI is calculated from infected plants divided by total plants. They still lack dated disease observations, plot-level DI counts, and a definition for the first reading group. The season statement and sowing-month value conflict, and the workbook irrigation entries conflict with the caption. The extracted rows are therefore useful as traceable research evidence but should not be converted into date-specific outcome labels or matched to daily weather as-is.

**Recommended next step:** request the original S14 field-survey sheet or protocol from the corresponding author, specifically asking for the first reading group's definition, actual field assessment dates, and the DI replicate counts used for each summary.
