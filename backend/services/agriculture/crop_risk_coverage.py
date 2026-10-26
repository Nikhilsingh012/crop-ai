"""Coverage inventory for source-backed and executable crop-risk rules."""
from collections import defaultdict

from services.agriculture.crop_risk_engine import HAZARDS, _finite, load_rule_records
from services.crop_catalog import load_catalog

SUPPORTED_EVALUATORS = {"hourly_threshold_exposure", "night_hourly_threshold_exposure", "hourly_temperature_condition_indicator", "daily_max_threshold_indicator", "daily_min_temperature_condition_indicator"}
SUPPORTED_PARAMETERS = {"temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m"}
SUPPORTED_UNITS = {
    "temperature_2m": {"deg c", "c", "°c", "f"},
    "relative_humidity_2m": {"%", "percent"},
    "precipitation": {"mm"},
    "wind_speed_10m": {"km h", "km/h", "m s", "m/s"},
}


def _execution_issues(rule):
    issues = []
    parameter = rule.get("weather_parameter")
    if rule.get("source_validation_status") != "verified":
        issues.append(f"source evidence is not verified ({rule.get('source_validation_status', 'unreviewed')})")
    if not str(rule.get("source_url", "")).startswith("https://") or not rule.get("publication_title"):
        issues.append("missing safe source metadata")
    if any(not rule.get(field) for field in ("publication_date", "evidence_excerpt", "last_reviewed")):
        issues.append("missing source evidence detail")
    if rule.get("evaluator") not in SUPPORTED_EVALUATORS:
        issues.append(f"unsupported evaluator {rule.get('evaluator')}")
    if parameter not in SUPPORTED_PARAMETERS:
        issues.append(f"unsupported forecast variable {parameter}")
    elif " ".join(str(rule.get("unit", "")).lower().replace("_", " ").replace("-", " ").split()) not in SUPPORTED_UNITS[parameter]:
        issues.append(f"unsupported unit {rule.get('unit')} for {parameter}")
    if _finite(rule.get("threshold")) is None or rule.get("operator") not in {"gt", "gte", "lt", "lte"}:
        issues.append("invalid threshold or operator")
    if rule.get("evaluator") == "daily_max_threshold_indicator":
        if rule.get("daily_field") != "temperature_max" or parameter != "temperature_2m":
            issues.append("daily Tmax evaluator requires temperature_max from temperature_2m")
        window = rule.get("forecast_window_days")
        minimum = rule.get("minimum_samples", window)
        if not isinstance(window, int) or not 1 <= window <= 7 or minimum != window:
            issues.append("invalid daily forecast window")
    elif rule.get("evaluator") == "hourly_temperature_condition_indicator":
        if parameter != "temperature_2m":
            issues.append("hourly temperature condition requires temperature_2m")
        window = rule.get("window_hours")
        minimum = rule.get("minimum_samples", window)
        if not isinstance(window, int) or not 1 <= window <= 168 or minimum != window:
            issues.append("invalid hourly condition forecast window")
    elif rule.get("evaluator") != "daily_min_temperature_condition_indicator":
        bands = rule.get("index_bands")
        if not isinstance(bands, list) or not bands or any(
            not isinstance(band, dict) or not isinstance(band.get("minimum"), int)
            or not isinstance(band.get("maximum"), int) or not band.get("label")
            for band in (bands or [])
        ):
            issues.append("missing or invalid severity bands")
        window = rule.get("window_hours", 48)
        minimum = rule.get("minimum_samples", window)
        if not isinstance(window, int) or not 1 <= window <= 168 or not isinstance(minimum, int) or not 1 <= minimum <= window:
            issues.append("invalid forecast window")
    elif rule.get("evaluator") == "daily_min_temperature_condition_indicator":
        if rule.get("daily_field") != "temperature_min" or parameter != "temperature_2m":
            issues.append("daily Tmin condition requires temperature_min from temperature_2m")
        window = rule.get("forecast_window_days")
        minimum = rule.get("minimum_samples", window)
        if not isinstance(window, int) or not 1 <= window <= 7 or minimum != window:
            issues.append("invalid daily minimum-temperature forecast window")
    if rule.get("evaluator") == "night_hourly_threshold_exposure" and parameter != "temperature_2m":
        issues.append("night evaluator requires temperature")
    return issues


def build_coverage_report():
    rules = load_rule_records()
    by_crop = defaultdict(list)
    for rule in rules:
        by_crop[rule.get("crop_id")].append(rule)
    hazard_codes = [code for code, _ in HAZARDS]
    rows = []
    for crop in load_catalog():
        crop_rules = by_crop.get(crop["crop_id"], [])
        verified = [rule for rule in crop_rules if rule.get("verification_status") == "verified"]
        executable = [rule for rule in verified if not _execution_issues(rule)]
        provisional = [rule for rule in crop_rules if rule.get("verification_status") != "verified"]
        invalid_citations = [rule for rule in crop_rules if rule.get("citation_status") == "claim_mismatch"]
        unverified_citations = [rule for rule in crop_rules if rule.get("citation_status") not in {"valid_authoritative", "claim_mismatch"}]
        incomplete_evidence = [rule for rule in crop_rules if rule.get("source_validation_status") in {"incomplete_evidence", "promising_incomplete"}]
        missing_weather_inputs = [rule for rule in crop_rules if rule.get("weather_parameter") not in SUPPORTED_PARAMETERS]
        unsupported_evaluators = [rule for rule in crop_rules if rule.get("evaluator") not in SUPPORTED_EVALUATORS]
        families = sorted({rule.get("hazard_type") for rule in executable if rule.get("hazard_type")})
        missing = [hazard for hazard in hazard_codes if hazard not in families]
        hazard_counts = {hazard: sum(1 for rule in crop_rules if rule.get("hazard_type") == hazard) for hazard in hazard_codes}
        non_executable = [rule for rule in verified if _execution_issues(rule)]
        rows.append({
            "crop_id": crop["crop_id"], "crop_name": crop["canonical_name"], "rule_count": len(crop_rules),
            "supported_stages": sorted({stage for rule in executable for stage in (rule.get("growth_stage") if isinstance(rule.get("growth_stage"), list) else [rule.get("growth_stage")]) if stage and stage != "all"}),
            "supported_hazard_families": families,
            "geographic_scope": sorted({scope for rule in executable for scope in (rule.get("region") if isinstance(rule.get("region"), list) else [rule.get("region")]) if scope}),
            "verified_rule_count": len(verified), "verified_executable_rule_count": len(executable),
            "verified_non_executable_rule_count": len(non_executable),
            "verified_non_executable_rules": [{"rule_id": r.get("rule_id"), "reasons": _execution_issues(r)} for r in non_executable],
            "provisional_rule_count": len(provisional), "rule_count_by_hazard": hazard_counts,
            "invalid_or_mismatched_citation_rule_ids": [r.get("rule_id") for r in invalid_citations],
            "unverified_citation_rule_ids": [r.get("rule_id") for r in unverified_citations],
            "incomplete_evidence_rule_ids": [r.get("rule_id") for r in incomplete_evidence],
            "missing_weather_input_rule_ids": [r.get("rule_id") for r in missing_weather_inputs],
            "unsupported_evaluator_rule_ids": [r.get("rule_id") for r in unsupported_evaluators],
            "rules_without_evaluator": [r.get("rule_id") for r in crop_rules if not r.get("evaluator")],
            "rules_with_unsupported_evaluator": [r.get("rule_id") for r in crop_rules if r.get("evaluator") and r.get("evaluator") not in SUPPORTED_EVALUATORS],
            "missing_hazard_families": missing,
            "missing_source_or_evaluator_requirements": [f"{r.get('rule_id')}: {reason}" for r in non_executable for reason in _execution_issues(r)],
            "coverage": "full" if len(families) == len(hazard_codes) else "partial" if executable else "none",
        })
    hazard_totals = {hazard: {
        "verified": sum(1 for r in rules if r.get("verification_status") == "verified" and r.get("hazard_type") == hazard),
        "verified_executable": sum(1 for r in rules if r.get("verification_status") == "verified" and r.get("hazard_type") == hazard and not _execution_issues(r)),
        "provisional": sum(1 for r in rules if r.get("verification_status") != "verified" and r.get("hazard_type") == hazard),
    } for hazard in hazard_codes}
    unavailable = [{"hazard": hazard, "reason": "No verified executable crop rule is registered."} for hazard in hazard_codes if not hazard_totals[hazard]["verified_executable"]]
    return {
        "schema_version": 1, "registry_rule_count": len(rules),
        "verified_rule_count": sum(row["verified_rule_count"] for row in rows),
        "verified_executable_rule_count": sum(row["verified_executable_rule_count"] for row in rows),
        "verified_non_executable_rule_count": sum(row["verified_non_executable_rule_count"] for row in rows),
        "provisional_rule_count": sum(row["provisional_rule_count"] for row in rows),
        "invalid_or_mismatched_citation_rule_count": sum(len(row["invalid_or_mismatched_citation_rule_ids"]) for row in rows),
        "unverified_citation_rule_count": sum(len(row["unverified_citation_rule_ids"]) for row in rows),
        "incomplete_evidence_rule_count": sum(len(row["incomplete_evidence_rule_ids"]) for row in rows),
        "missing_weather_input_rule_count": sum(len(row["missing_weather_input_rule_ids"]) for row in rows),
        "unsupported_evaluator_rule_count": sum(len(row["unsupported_evaluator_rule_ids"]) for row in rows),
        "rule_count_by_hazard": hazard_totals, "unavailable_hazards": unavailable,
        "provider_fields": sorted(SUPPORTED_PARAMETERS), "crops": rows,
    }


def print_coverage_report():
    report = build_coverage_report()
    print(f"Crop risk coverage: {len(report['crops'])} crops; {report['verified_executable_rule_count']} verified executable rules; {report['provisional_rule_count']} provisional rules")
    for row in report["crops"]:
        if row["rule_count"]:
            print(f"{row['crop_id']}: {row['coverage']} | executable={row['verified_executable_rule_count']} non_executable={row['verified_non_executable_rule_count']} provisional={row['provisional_rule_count']} hazards={','.join(row['supported_hazard_families']) or 'none'} missing={','.join(row['missing_hazard_families'])}")


if __name__ == "__main__":
    print_coverage_report()
