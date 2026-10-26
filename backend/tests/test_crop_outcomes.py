"""Validator fixtures below are synthetic test cases, never training observations."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.crop_outcomes import REQUIRED_COLUMNS, validate_csv, validate_row


def fixture_record():
    # TEST FIXTURE ONLY: invented solely to exercise validation; not a real study record.
    return {
        "source_url": "https://example.invalid/test-fixture", "source_citation": "TEST FIXTURE ONLY",
        "publisher": "TEST FIXTURE ONLY", "original_record_id": "TEST-ONLY-001",
        "observation_date": "2024-06-01", "crop": "Rice", "state": "TEST", "district": "TEST",
        "location_description": "TEST FIXTURE ONLY", "latitude": "20", "longitude": "80",
        "growth_stage": "TEST FIXTURE ONLY", "outcome_type": "disease_observation",
        "hazard_or_disease": "TEST FIXTURE ONLY", "label_status": "positive",
        "label_basis": "TEST FIXTURE ONLY", "negative_assessment_method": "",
        "severity": "moderate", "severity_scale": "TEST FIXTURE ONLY",
        "measured_loss_value": "", "measured_loss_unit": "",
        "verification_status": "unverified", "uncertainty": "unknown",
        "uncertainty_notes": "TEST FIXTURE ONLY; not real data",
    }


class CropOutcomeValidationTests(unittest.TestCase):
    def test_valid_fixture_is_preparation_only_and_original_csv_is_unchanged(self):
        fixture = fixture_record()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test-fixture.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS)
                writer.writeheader()
                writer.writerow(fixture)
            original_bytes = path.read_bytes()
            report = validate_csv(path)
            self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(report["record_counts"]["validated_records_ready_for_review"], 1)
        self.assertFalse(report["database_import_performed"])
        self.assertEqual(report["training_store_imported_records"], 0)

    def test_alias_is_reported_as_noncanonical_without_rewriting_input(self):
        row = fixture_record()
        row["crop"] = "paddy"
        self.assertTrue(any(error.startswith("crop_must_use_catalog_canonical_name") for error in validate_row(row, 2)))
        self.assertEqual(row["crop"], "paddy")

    def test_negative_requires_explicit_method_and_not_absence_of_reporting(self):
        row = fixture_record()
        row.update(label_status="negative", severity="", severity_scale="", negative_assessment_method="no report")
        self.assertIn("negative_label_requires_explicit_assessment_method_not_absence_of_reporting", validate_row(row, 2))
        row["negative_assessment_method"] = "documented diagnostic survey protocol TEST FIXTURE ONLY"
        self.assertNotIn("negative_label_requires_explicit_assessment_method_not_absence_of_reporting", validate_row(row, 2))

    def test_invalid_provenance_date_coordinates_duplicate_and_labels_reported(self):
        row = fixture_record()
        row.update(source_url="file://private", source_citation="", observation_date="01/06/2024",
                   latitude="91", longitude="200", label_status="healthy", verification_status="guessed")
        failures = validate_row(row, 2)
        for expected in ("source_url_must_be_http_or_https", "observation_date_must_be_iso_yyyy_mm_dd",
                         "invalid_latitude", "invalid_longitude", "label_status_must_be_positive_negative_or_unknown",
                         "invalid_verification_status"):
            self.assertIn(expected, failures)

    def test_header_only_template_reports_zero_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty-template.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS).writeheader()
            report = validate_csv(path)
        self.assertEqual(report["record_counts"]["rows_read"], 0)
        self.assertEqual(report["record_counts"]["validated_records_ready_for_review"], 0)
        self.assertEqual(report["label_counts_as_submitted"]["unknown_or_missing"], 0)

    def test_duplicate_original_record_id_is_not_silently_removed(self):
        one, two = fixture_record(), fixture_record()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test-fixture.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS)
                writer.writeheader()
                writer.writerows((one, two))
            report = validate_csv(path)
        self.assertEqual(report["record_counts"]["rows_read"], 2)
        self.assertEqual(report["record_counts"]["records_with_validation_failures"], 1)
        self.assertEqual(report["validation_failures"][0]["row"], 3)
        self.assertTrue(any("duplicate_publisher_record_id" in e for e in report["validation_failures"][0]["errors"]))


if __name__ == "__main__":
    unittest.main()
