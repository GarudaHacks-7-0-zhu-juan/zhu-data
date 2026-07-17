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


class PowerBiTest(unittest.TestCase):
    def test_parse_rows_decodes_dictionaries_repetition_and_nulls(self):
        response = {
            "results": [{"result": {"data": {"dsr": {"DS": [{
                "IC": True,
                "ValueDicts": {"D0": ["A"], "D1": ["X", "Y"]},
                "PH": [{"DM0": [
                    {"S": [{"DN": "D0"}, {"DN": "D1"}, {}], "C": [0, 0, 5]},
                    {"R": 1, "C": [1, 3]},
                    {"Ø": 1, "C": [0, 2]},
                ]}],
            }]}}}}]
        }

        self.assertEqual(
            pipeline.parse_rows(response),
            [["A", "X", 5], ["A", "Y", 3], [None, "X", 2]],
        )

    def test_parse_rows_rejects_truncated_results(self):
        response = {
            "results": [{"result": {"data": {"dsr": {"DS": [{
                "IC": False,
                "PH": [{"DM0": [{"S": [{}], "C": [1]}]}],
            }]}}}}]
        }

        with self.assertRaisesRegex(ValueError, "truncated"):
            pipeline.parse_rows(response)

    def test_powerbi_literals_support_nulls_numbers_and_quotes(self):
        self.assertEqual(pipeline.pbi_literal(None), "null")
        self.assertEqual(pipeline.pbi_literal(2026), "2026L")
        self.assertEqual(pipeline.pbi_literal("POLDA METRO JAYA"), "'POLDA METRO JAYA'")
        self.assertEqual(pipeline.pbi_literal("O'HARA"), "'O''HARA'")


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

    def test_hierarchy_outputs_reconcile_and_cover_all_districts(self):
        def read_csv(name):
            with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
                return list(csv.DictReader(f))

        raw = read_csv("crime_polsek_kecamatan_types.csv")
        aggregated = read_csv("crime_kecamatan_types.csv")
        unmatched = read_csv("crime_unmatched_locations.csv")
        latest_summary = read_csv("crime_kecamatan.csv")

        raw_total = sum(int(row["crime_total"]) for row in raw)
        aggregated_total = sum(int(row["crime_total"]) for row in aggregated)
        unmapped_location_total = sum(
            int(row["crime_total"])
            for row in unmatched
            if row["reason"] != "blank crime type"
        )
        self.assertEqual(raw_total, aggregated_total + unmapped_location_total)
        self.assertEqual({row["polda"] for row in raw}, {"POLDA METRO JAYA"})
        self.assertEqual(len({row["kecamatan"] for row in aggregated}), 44)

        years = sorted({int(row["year"]) for row in aggregated})
        latest_year = years[-1]
        self.assertEqual({int(row["crime_year"]) for row in latest_summary}, {latest_year})
        latest_aggregate_total = sum(
            int(row["crime_total"])
            for row in aggregated
            if int(row["year"]) == latest_year
        )
        self.assertEqual(
            latest_aggregate_total,
            sum(int(row["crime_total"]) for row in latest_summary),
        )
        self.assertTrue(any(row["jenis_kejahatan"] == "UNCLASSIFIED" for row in aggregated))


if __name__ == "__main__":
    unittest.main()
