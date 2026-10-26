import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from uganda_dataset_feasibility_audit import analyze_dataset


class UgandaDatasetFeasibilityAuditTests(unittest.TestCase):
    def test_plant_rows_group_by_field_but_keep_plant_eligibility(self):
        headers = ["id", "plant_id", "date", "latitude", "longitude", "cbsd_foliar_presence"]
        rows = [
            {"id": "f1", "plant_id": "1", "date": "7/27/2004", "latitude": "0.5", "longitude": "31", "cbsd_foliar_presence": "1"},
            {"id": "f1", "plant_id": "2", "date": "7/27/2004", "latitude": "0.5", "longitude": "31", "cbsd_foliar_presence": "0"},
            {"id": "f2", "plant_id": "1", "date": "NA", "latitude": "0.6", "longitude": "31", "cbsd_foliar_presence": "NA"},
        ]
        result = analyze_dataset("A", headers, rows, "plant-level rows nested in field ID", ("date",), ("cbsd_foliar_presence",))
        self.assertEqual(result["weather_eligible_rows"], 2)
        self.assertEqual(result["weather_eligible_unique_ids"], 1)
        self.assertEqual(result["weather_eligible_unique_location_dates"], 1)
        self.assertEqual(result["weather_eligible_field_visit_records"], 1)
        self.assertEqual(result["disease_label_availability"]["cbsd_foliar_presence"]["nonmissing"], 2)

    def test_year_only_dataset_is_not_date_eligible(self):
        headers = ["id", "year", "latitude", "longitude", "cbsd_foliar_incidence"]
        rows = [{"id": "b1", "year": "2008", "latitude": "1", "longitude": "32", "cbsd_foliar_incidence": "0"}]
        result = analyze_dataset("B", headers, rows, "field summary", (), ("cbsd_foliar_incidence",))
        self.assertIsNone(result["date_column"])
        self.assertEqual(result["weather_eligible_rows"], 0)
        self.assertEqual(result["valid_coordinate_count"], 1)

    def test_duplicate_records_and_location_date_dedup_are_distinguished(self):
        headers = ["id", "date", "latitude", "longitude", "data_origin", "cbsd_foliar_incidence"]
        rows = [
            {"id": "c1", "date": "2004-07-27", "latitude": "0.5", "longitude": "31", "data_origin": "dbA", "cbsd_foliar_incidence": "0.2"},
            {"id": "c2", "date": "2004-07-27", "latitude": "0.5", "longitude": "31", "data_origin": "dbA", "cbsd_foliar_incidence": "0.4"},
            {"id": "c2", "date": "2004-07-27", "latitude": "0.5", "longitude": "31", "data_origin": "dbA", "cbsd_foliar_incidence": "0.4"},
        ]
        result = analyze_dataset("C", headers, rows, "field record", ("date",), ("cbsd_foliar_incidence",))
        self.assertEqual(result["weather_eligible_rows"], 3)
        self.assertEqual(result["weather_eligible_unique_ids"], 2)
        self.assertEqual(result["weather_eligible_unique_location_dates"], 1)
        self.assertEqual(result["exact_duplicate_rows"], 1)
        self.assertEqual(result["repeated_id_group_count"], 1)

    def test_conflicting_dates_under_one_field_id_are_reported_not_collapsed(self):
        headers = ["id", "plant_id", "date", "latitude", "longitude"]
        rows = [
            {"id": "f1", "plant_id": "1", "date": "7/16/2015", "latitude": "0.9", "longitude": "33"},
            {"id": "f1", "plant_id": "2", "date": "7/17/2015", "latitude": "0.9", "longitude": "33"},
        ]
        result = analyze_dataset("A", headers, rows, "plant-level rows nested in field ID", ("date",), ())
        self.assertEqual(result["weather_eligible_unique_ids"], 1)
        self.assertEqual(result["field_id_conflicting_eligible_date_coordinate_groups"], 1)
        self.assertEqual(result["field_level_unique_location_dates"], 2)
        self.assertEqual(result["date_year_conflict_count"], 0)


if __name__ == "__main__":
    unittest.main()
