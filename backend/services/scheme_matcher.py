"""Deterministic, conservative matching against reviewed scheme records."""
from datetime import datetime, timezone


MAX_SOURCE_AGE_DAYS = 180


def _rule_groups(rules):
    if not isinstance(rules, dict):
        return None
    groups = (rules.get("required", []), rules.get("excluded_if", []), rules.get("official_review_if", []))
    if not all(isinstance(group, list) and all(isinstance(rule, dict) for rule in group) for group in groups):
        return None
    return groups


def _is_stale(last_checked_at, now=None):
    if not last_checked_at:
        return True
    checked = last_checked_at
    if isinstance(checked, str):
        try:
            checked = datetime.fromisoformat(checked.replace("Z", "+00:00"))
        except ValueError:
            return True
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return (current - checked).days > MAX_SOURCE_AGE_DAYS


def match_scheme(scheme, answers, state=None, now=None):
    """Return a transparent result; answers are caller supplied, never persisted."""
    result = {
        "scheme_id": scheme["scheme_id"],
        "official_name": scheme["official_name"],
        "status": "cannot_determine",
        "reasons": [],
        "missing_information": [],
        "verification_status": scheme.get("verification_status", "unverified"),
        "last_checked_at": scheme.get("last_checked_at"),
        "application_status": scheme.get("application_status", "unknown"),
        "deadline": scheme.get("deadline"),
        "official_application_url": scheme.get("official_application_url"),
        "official_source_url": scheme.get("official_source_url"),
    }
    if result["verification_status"] != "verified" or _is_stale(result["last_checked_at"], now):
        result["verification_status"] = "stale" if result["verification_status"] == "verified" else result["verification_status"]
        result["reasons"].append("Eligibility information is not currently verified; check the official source.")
        return result

    scope = scheme.get("state_scope")
    if scope and (not state or state.casefold() not in {str(item).casefold() for item in scope}):
        result["status"] = "does_not_match" if state else "cannot_determine"
        result["reasons"].append("This scheme has a state-specific scope; confirm the relevant state on its official page." if not state else "The saved state is outside this scheme's recorded scope.")
        return result

    groups = _rule_groups(scheme.get("eligibility_rules"))
    if groups is None:
        result["reasons"].append("The verified scheme record does not contain rules in a supported structured format.")
        return result
    required, excluded, review = groups
    unresolved = False
    for rule in required:
        field, value = rule.get("field"), answers.get(rule.get("field"))
        if value is None:
            result["missing_information"].append({"field": field, "question": rule.get("label", field)})
            unresolved = True
        elif value != rule.get("value"):
            result["status"] = "does_not_match"
            result["reasons"].append(rule.get("label", "A required criterion is not met."))
            return result
    for rule in excluded:
        field, value = rule.get("field"), answers.get(rule.get("field"))
        if value is None:
            result["missing_information"].append({"field": field, "question": rule.get("label", field)})
            unresolved = True
        elif value == rule.get("value"):
            result["status"] = "does_not_match"
            result["reasons"].append(rule.get("label", "A published exclusion applies."))
            return result
    review_required = False
    for rule in review:
        if answers.get(rule.get("field")) is True:
            review_required = True
            result["reasons"].append(rule.get("label", "An official review is needed."))
        elif answers.get(rule.get("field")) is None:
            result["missing_information"].append({"field": rule.get("field"), "question": rule.get("label", rule.get("field"))})
            unresolved = True

    if review_required:
        result["status"] = "possibly_eligible"
        result["reasons"].append("An official authority must review this case; this flag is not an automatic exclusion.")
    elif unresolved:
        result["status"] = "possibly_eligible"
        result["reasons"].append("More information is needed to compare the case with all published criteria.")
    else:
        result["status"] = "likely_matches"
        result["reasons"].append("The supplied answers match the currently reviewed criteria. The department makes the final eligibility decision.")
    return result
