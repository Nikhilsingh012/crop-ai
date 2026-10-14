import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.scheme_matcher import match_scheme


NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
RULES = {
    "required": [{"field": "landholding_family", "value": True, "label": "Landholding family"}],
    "excluded_if": [{"field": "income_tax_payer", "value": True, "label": "Income tax exclusion"}],
    "official_review_if": [{"field": "recent_land", "value": True, "label": "Needs physical review"}],
}


def scheme(**updates):
    result = {
        "scheme_id": "test-scheme", "official_name": "Test scheme",
        "verification_status": "verified", "application_status": "unknown",
        "last_checked_at": NOW - timedelta(days=1), "eligibility_rules": RULES,
        "state_scope": None, "deadline": None,
        "official_application_url": "https://example.gov.in/apply",
        "official_source_url": "https://example.gov.in/",
    }
    result.update(updates)
    return result


class SchemeMatcherTests(unittest.TestCase):
    def test_missing_answers_are_possible_not_approved(self):
        result = match_scheme(scheme(), {}, now=NOW)
        self.assertEqual(result["status"], "possibly_eligible")
        self.assertGreater(len(result["missing_information"]), 0)

    def test_required_criterion_false_does_not_match(self):
        result = match_scheme(scheme(), {"landholding_family": False}, now=NOW)
        self.assertEqual(result["status"], "does_not_match")

    def test_exclusion_and_official_review_are_handled_separately(self):
        answers = {"landholding_family": True, "income_tax_payer": True, "recent_land": False}
        self.assertEqual(match_scheme(scheme(), answers, now=NOW)["status"], "does_not_match")
        answers["income_tax_payer"] = False
        answers["recent_land"] = True
        self.assertEqual(match_scheme(scheme(), answers, now=NOW)["status"], "possibly_eligible")

    def test_likely_result_requires_every_rule_and_official_review_is_final(self):
        answers = {"landholding_family": True, "income_tax_payer": False, "recent_land": False}
        result = match_scheme(scheme(), answers, now=NOW)
        self.assertEqual(result["status"], "likely_matches")
        self.assertIn("final eligibility decision", result["reasons"][-1].casefold())

    def test_unverified_or_stale_rules_never_create_match(self):
        answers = {"landholding_family": True, "income_tax_payer": False, "recent_land": False}
        self.assertEqual(match_scheme(scheme(verification_status="unverified"), answers, now=NOW)["status"], "cannot_determine")
        self.assertEqual(match_scheme(scheme(last_checked_at=NOW-timedelta(days=181)), answers, now=NOW)["status"], "cannot_determine")

    def test_state_scope_needs_saved_state_or_matching_scope(self):
        scoped = scheme(state_scope=["Bihar"])
        self.assertEqual(match_scheme(scoped, {}, now=NOW)["status"], "cannot_determine")
        self.assertEqual(match_scheme(scoped, {}, state="Maharashtra", now=NOW)["status"], "does_not_match")


if __name__ == "__main__":
    unittest.main()
