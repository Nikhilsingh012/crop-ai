Put an ImageFolder-compatible dataset here:

- data/train/<crop>\_\_\_<disease>/\*.jpg
- data/val/<crop>\_\_\_<disease>/\*.jpg

Do not commit private or licensed image datasets to this repository.

## Crop knowledge sources

Place trusted crop-specific `.pdf`, `.csv`, `.json`, `.txt`, or `.md` references under `data/crop_knowledge/sources/`. Every source file must have a neighboring metadata sidecar named by appending `.metadata.json` to the full filename (for example, `guide.pdf.metadata.json`). The sidecar must identify a registered `crop_id`, source title, and `source_url`; it can also include `region`, `stage`, and `risk_type`. The ingestion command checks crop IDs and URL syntax, extracts text, and stores crop ID metadata in the local index. It does not verify remote URLs or promote a crop's knowledge status. PDF extraction uses `pypdf`; scanned image-only PDFs need OCR before ingestion. Only add source links after confirming the cited document supports the attached text.

Example sidecar:

```json
{
  "crop_id": "rice",
  "source": "State agricultural university advisory",
  "source_url": "https://example.org/advisory.pdf",
  "region": "Odisha",
  "stage": "flowering",
  "risk_type": "high_humidity"
}
```

To enable a numerical risk assessment, a maintainer must separately review source-backed thresholds, add them to that crop's structured knowledge record, set `threshold_evidence_status` to `verified`, and list only the supported types in the central catalog. Until then, the record remains `LIMITED` and analysis has no score.

Location forecasts can still surface general heavy-rainfall exposure signals based on the IMD rainfall categories. These signals describe weather intensity only; they do not determine crop damage or replace current district warnings. See [the crop-risk system notes](../docs/crop-risk-system.md) for their limits and source.
