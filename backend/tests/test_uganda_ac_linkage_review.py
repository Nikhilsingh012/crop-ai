import unittest

from scripts.uganda_ac_linkage_review import build_review, classify, read_csv


class UgandaACLinkageReviewTests(unittest.TestCase):
    def test_classification_is_conservative(self):
        self.assertEqual(
            classify("A_FIELD_SIGNATURE_CONFLICT"),
            ("unresolved", "exclude temporarily; manual review required before field-visit matching"),
        )
        self.assertEqual(classify("AC_COORDINATE_DISCREPANCY")[0], "unresolved")
        with self.assertRaises(ValueError):
            classify("COORDINATE_CLOSE")

    def test_real_review_has_expected_disputes_and_is_deterministic(self):
        a_rows = read_csv("DATASET_A.csv")
        c_rows = read_csv("DATASET_C.csv")
        first = build_review(a_rows, c_rows)
        second = build_review(a_rows, c_rows)
        self.assertEqual(first, second)
        self.assertEqual(first["disputed_linkage_count"], 14)
        by_type = {}
        for row in first["disputes"]:
            by_type[row["dispute_type"]] = by_type.get(row["dispute_type"], 0) + 1
            self.assertEqual(row["classification"], "unresolved")
        self.assertEqual(by_type, {"A_FIELD_SIGNATURE_CONFLICT": 3, "AC_COORDINATE_DISCREPANCY": 11})

    def test_conflict_records_retain_all_plant_rows(self):
        review = build_review(read_csv("DATASET_A.csv"), read_csv("DATASET_C.csv"))
        conflicts = [row for row in review["disputes"] if row["dispute_type"] == "A_FIELD_SIGNATURE_CONFLICT"]
        for row in conflicts:
            import json
            source_rows = json.loads(row["A_source_rows"])
            self.assertTrue(len(source_rows) >= 29)
            self.assertTrue(all(source["id"] == row["A_id"] for source in source_rows))


if __name__ == "__main__":
    unittest.main()
