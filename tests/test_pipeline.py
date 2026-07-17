import copy
import csv
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pipeline


class RiskScoringTest(unittest.TestCase):
    def test_percentile_ranks_average_ties(self):
        rows = [{"value": 1}, {"value": 2}, {"value": 2}, {"value": 4}]

        self.assertEqual(pipeline.percentile_ranks(rows, "value"), [0.0, 0.5, 0.5, 1.0])

    def test_risk_level_thresholds(self):
        self.assertEqual(pipeline.risk_level(0.0), "NONE")
        self.assertEqual(pipeline.risk_level(0.2), "LOW")
        self.assertEqual(pipeline.risk_level(0.4), "MEDIUM")
        self.assertEqual(pipeline.risk_level(0.7), "HIGH")
        self.assertEqual(pipeline.risk_level(0.9), "CRITICAL")

    def test_scoring_is_deterministic(self):
        rows = [
            {"kecamatan": "A", "street_crime": 10, "street_crime_per_100k": 30, "street_crime_evening": 5},
            {"kecamatan": "B", "street_crime": 20, "street_crime_per_100k": 20, "street_crime_evening": 10},
            {"kecamatan": "C", "street_crime": 30, "street_crime_per_100k": 10, "street_crime_evening": 15},
        ]
        expected = copy.deepcopy(rows)

        pipeline.score_rows(rows)
        pipeline.score_rows(expected)

        self.assertEqual(rows, expected)
        self.assertEqual(rows[0]["risk_policy_version"], "jakarta-kecamatan-v1")


class GeneratedArtifactsTest(unittest.TestCase):
    def test_csv_and_geojson_have_matching_risk_properties(self):
        with open(os.path.join(ROOT, "data", "master_dataset.csv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        with open(os.path.join(ROOT, "data", "kecamatan_boundaries.geojson"), encoding="utf-8") as f:
            features = json.load(f)["features"]

        self.assertEqual(len(rows), 44)
        self.assertEqual(len(features), 44)
        csv_by_kecamatan = {row["kecamatan"]: row for row in rows}
        self.assertEqual(len(csv_by_kecamatan), 44)

        for feature in features:
            props = feature["properties"]
            csv_row = csv_by_kecamatan[props["kecamatan"]]
            self.assertEqual(props["risk_score"], float(csv_row["risk_score"]))
            self.assertEqual(props["risk_level"], csv_row["risk_level"])
            self.assertEqual(props["risk_policy_version"], csv_row["risk_policy_version"])
            self.assertGreaterEqual(props["risk_score"], 0)
            self.assertLessEqual(props["risk_score"], 1)


if __name__ == "__main__":
    unittest.main()
