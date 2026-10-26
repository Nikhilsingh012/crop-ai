#!/usr/bin/env python3
"""Build a read-only, deterministic review of disputed Uganda A/C linkages."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/crop_outcomes/source_files/uganda_cassava_brown_streak"
OUT = ROOT / "data/crop_outcomes/processed/uganda_cassava_brown_streak/linkage_review"


def read_csv(name: str) -> list[dict[str, str]]:
    with (SOURCE / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_date(value: str) -> str | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except (ValueError, AttributeError):
            pass
    return None


def classify(kind: str) -> tuple[str, str]:
    if kind == "A_FIELD_SIGNATURE_CONFLICT":
        return "unresolved", "exclude temporarily; manual review required before field-visit matching"
    if kind == "AC_COORDINATE_DISCREPANCY":
        return "unresolved", "manual review; exclude from a combined A/C field-visit match pending coordinate adjudication"
    raise ValueError(f"Unsupported dispute type: {kind}")


def _row_details(row: dict[str, str], source_row: int, dataset: str) -> dict[str, object]:
    fields = (["id", "plant_id", "date", "year", "latitude", "longitude", "district", "village",
               "cbsd_foliar_presence", "cbsd_foliar_severity"] if dataset == "A" else
              ["id", "dbA_id", "dbB_id", "data_origin", "matched", "date", "year", "latitude", "longitude",
               "district", "village", "cbsd_foliar_incidence", "cbsd_foliar_severity_mean"])
    result: dict[str, object] = {"source_row_number_header_is_1": source_row}
    result.update({key: row.get(key, "") for key in fields})
    result["parsed_date"] = parse_date(row.get("date", ""))
    return result


def build_review(a_rows: list[dict[str, str]], c_rows: list[dict[str, str]]) -> dict[str, object]:
    a_by_id: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for i, row in enumerate(a_rows, 2):
        a_by_id.setdefault(row["id"], []).append((i, row))
    c_by_aid: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for i, row in enumerate(c_rows, 2):
        if row.get("dbA_id", "").strip():
            c_by_aid.setdefault(row["dbA_id"].strip(), []).append((i, row))

    disputes: list[dict[str, object]] = []
    conflict_ids = ("2015046", "2015079", "2015173")
    for field_id in conflict_ids:
        group = a_by_id[field_id]
        signatures = sorted({(parse_date(r.get("date", "")), r.get("latitude", ""), r.get("longitude", "")) for _, r in group})
        kind = "A_FIELD_SIGNATURE_CONFLICT"
        classification, recommendation = classify(kind)
        disputes.append({
            "dispute_id": f"A-ID-{field_id}", "dispute_type": kind, "classification": classification,
            "recommendation": recommendation, "A_id": field_id, "C_id": "", "C_dbA_id": "",
            "linkage_field": "A.id (field ID; repeated plant rows) — no C row is being merged by proximity",
            "dates": json.dumps([x[0] for x in signatures], separators=(",", ":")),
            "A_signatures": json.dumps([{"date": d, "latitude": float(lat), "longitude": float(lon)} for d, lat, lon in signatures], separators=(",", ":")),
            "C_coordinates": "", "coordinate_difference_latitude": "", "coordinate_difference_longitude": "",
            "distance_m_approx": "", "A_source_rows": json.dumps([_row_details(r, i, "A") for i, r in group], separators=(",", ":")),
            "C_linked_source_rows": json.dumps([_row_details(r, i, "C") for i, r in c_by_aid.get(field_id, [])], separators=(",", ":")),
            "C_source_row": "", "evidence": "All A rows under this id and linked C rows were inspected. C.dbA_id links by field ID; its date agrees with one A signature, but the legend documents no independent date adjudication or rule identifying the preferred A visit signature. matched=NO is not a validation status. Keep the A visit unresolved.",
        })

    mismatches: list[tuple[str, int, dict[str, str], int, dict[str, str]]] = []
    for aid, cgroup in c_by_aid.items():
        agroup = a_by_id.get(aid, [])
        for ci, c in cgroup:
            cd = parse_date(c.get("date", ""))
            if cd is None:
                continue
            c_lat, c_lon = float(c["latitude"]), float(c["longitude"])
            signatures = {(parse_date(a.get("date", "")), float(a["latitude"]), float(a["longitude"])) for _, a in agroup if parse_date(a.get("date", "")) == cd}
            if signatures and not any(lat == c_lat and lon == c_lon for _, lat, lon in signatures):
                # Source group already has a unique matching date signature for these audited cases.
                ai, ar = next((ai, ar) for ai, ar in agroup if parse_date(ar.get("date", "")) == cd)
                mismatches.append((aid, ci, c, ai, ar))
    mismatches.sort(key=lambda item: (item[0], item[1]))
    if len(mismatches) != 11:
        raise ValueError(f"Expected 11 date-matched A/C coordinate discrepancies from audited source snapshot; found {len(mismatches)}")
    for aid, ci, c, ai, a in mismatches:
        kind = "AC_COORDINATE_DISCREPANCY"
        classification, recommendation = classify(kind)
        alat, alon = float(a["latitude"]), float(a["longitude"])
        clat, clon = float(c["latitude"]), float(c["longitude"])
        # Haversine distance is descriptive only; it is not a linkage rule.
        from math import asin, cos, radians, sin, sqrt
        dlat, dlon = clat - alat, clon - alon
        h = sin(radians(dlat) / 2) ** 2 + cos(radians(alat)) * cos(radians(clat)) * sin(radians(dlon) / 2) ** 2
        distance = 6371000 * 2 * asin(sqrt(h))
        disputes.append({
            "dispute_id": f"AC-{aid}-{c['id']}", "dispute_type": kind, "classification": classification,
            "recommendation": recommendation, "A_id": aid, "C_id": c["id"], "C_dbA_id": c["dbA_id"],
            "linkage_field": "C.dbA_id = A.id (documented field-ID linkage)",
            "dates": parse_date(c["date"]), "A_signatures": json.dumps([{"date": parse_date(a["date"]), "latitude": alat, "longitude": alon}], separators=(",", ":")),
            "C_coordinates": json.dumps({"latitude": clat, "longitude": clon}, separators=(",", ":")),
            "coordinate_difference_latitude": clat - alat, "coordinate_difference_longitude": clon - alon,
            "distance_m_approx": round(distance, 1),
            "A_source_rows": json.dumps([_row_details(r, i, "A") for i, r in a_by_id[aid]], separators=(",", ":")),
            "C_linked_source_rows": "",
            "C_source_row": json.dumps(_row_details(c, ci, "C"), separators=(",", ":")),
            "evidence": f"C.dbA_id links C.id to A.id by documented field ID; survey dates agree, coordinates differ by about {distance:.1f} m, and district labels differ (A={a.get('district','')}; C={c.get('district','')}). Village labels are {a.get('village','')} and {c.get('village','')}; same-name villages do not resolve the coordinate conflict. The audit and legend provide no correction history or preferred-source rule. Distance is descriptive only and was not used to merge or choose coordinates.",
        })
    disputes.sort(key=lambda row: row["dispute_id"])
    return {"review_version": 1, "source_files": ["DATASET_A.csv", "DATASET_C.csv"],
            "disputed_linkage_count": len(disputes), "classification_counts": {"unresolved": len(disputes)},
            "recommendation_counts": {"exclude_temporarily_or_manual_review": len(disputes)},
            "policy": "Preserve both source values. Link only via documented C.dbA_id to A.id. Coordinate proximity is not linkage evidence. No weather data were requested.",
            "disputes": disputes}


def write_outputs(review: dict[str, object], out_dir: Path = OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "ac_linkage_review.json"
    csv_path = out_dir / "ac_linkage_review.csv"
    json_path.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = review["disputes"]
    columns = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    a_conflicts = [row for row in rows if row["dispute_type"] == "A_FIELD_SIGNATURE_CONFLICT"]
    ac_conflicts = [row for row in rows if row["dispute_type"] == "AC_COORDINATE_DISCREPANCY"]
    lines = [
        "# Uganda cassava A/C linkage review", "",
        "Read-only, deterministic review of original Dataset A and Dataset C rows. No weather API calls were made; source files and the 10-row weather pilot were not changed.", "",
        "## Decision", "",
        "All 14 disputed cases remain unresolved. Temporarily exclude the three A field IDs from field-visit weather matching because each contains conflicting actual date signatures. Send all 11 linked A/C coordinate discrepancies for manual review and exclude them from combined A/C field-visit matching pending coordinate adjudication. No coordinate or date was selected. A C-only weather extraction would retain C's own provenance and coordinates but would not reconcile its linked A record.", "",
        "## A field IDs with conflicting signatures", "",
        "Each field ID has 30 associated plant source rows. CSV and JSON include every A source row (line number, plant_id, actual date, coordinates, location labels, and disease labels) and the linked C row. C's date agreeing with one A signature does not adjudicate A: C is linked by ID and is not an independent correction record; matched=NO is not a validation status.", "",
        "| A.id | Actual date/location signatures | A source rows | Linked C date/location | Decision |", "|---|---|---:|---|---|",
    ]
    for row in a_conflicts:
        crows = json.loads(row["C_linked_source_rows"])
        cbrief = "; ".join(f"{x['date']} ({x['latitude']}, {x['longitude']}; {x['district']}/{x['village']})" for x in crows)
        lines.append(f"| {row['A_id']} | `{row['A_signatures']}` | {len(json.loads(row['A_source_rows']))} | {cbrief} | unresolved; exclude temporarily |")
        lines += ["", "## Linked A/C coordinate discrepancies", "", "Linkage uses documented `C.dbA_id = A.id`. All 11 dates are 2014-12-29. Deltas below are C minus A; Haversine distances are descriptive only and were not used to infer identity or choose a point. District labels differ in every case: C says KIBAALE, while A says MUBENDE for IDs 11625-11633 and KYEGEGWA for IDs 11635-11636. Village strings match, but that does not establish the correct coordinate. All C rows have data_origin=dbA and matched=NO. Existing documentation gives no correction history, coordinate precision rule, or preferred-source rule.", "", "| A.id / C.id | Village | A coordinate (lat, lon) | C coordinate (lat, lon) | dLat | dLon | Approx distance | A district to C district |", "|---|---|---|---|---:|---:|---:|---|"]
    for row in ac_conflicts:
        arow = json.loads(row["A_source_rows"])[0]
        crow = json.loads(row["C_source_row"])
        lines.append(f"| {row['A_id']} / {row['C_id']} | {arow['village']} | ({arow['latitude']}, {arow['longitude']}) | ({crow['latitude']}, {crow['longitude']}) | {row['coordinate_difference_latitude']:.6f} | {row['coordinate_difference_longitude']:.6f} | {row['distance_m_approx']:.1f} m | {arow['district']} to {crow['district']} |")
    lines += ["", "Every case is unresolved and requires manual review before combined field-visit matching. Complete source-row evidence is in `data/crop_outcomes/processed/uganda_cassava_brown_streak/linkage_review/ac_linkage_review.csv` and `.json`.", "", "## Reproducibility and constraints", "", "Run `python scripts/uganda_ac_linkage_review.py` from the repository root to rebuild the deterministic CSV, JSON, and this report from the original A/C files. No matching by coordinate proximity or year is performed. No NASA POWER requests were made, and the pilot and source data were not modified.", ""]
    (ROOT / "docs/uganda_ac_linkage_review.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    review = build_review(read_csv("DATASET_A.csv"), read_csv("DATASET_C.csv"))
    write_outputs(review, args.output_dir)
    print(f"Disputes: {review['disputed_linkage_count']}; unresolved: {review['classification_counts']['unresolved']}")


if __name__ == "__main__":
    main()
