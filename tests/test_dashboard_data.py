import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_dashboard_data.py"
SPEC = importlib.util.spec_from_file_location("build_dashboard_data", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class DashboardDataTest(unittest.TestCase):
    def test_pearson_ignores_missing_by_accepting_only_pairs(self):
        self.assertEqual(MODULE.pearson([(1, 1), (2, 2), (3, 3)]), 1.0)
        self.assertIsNone(MODULE.pearson([(1, 1), (2, 2)]))

    def test_not_mentioned_is_not_zero(self):
        rows = []
        for theme in MODULE.THEMES:
            rows.append(
                {
                    "pub_date": "2026-01-01",
                    "theme": theme,
                    "score": None,
                    "assessment": "not_mentioned",
                    "confidence": "low",
                    "evidence_count": 0,
                    "taxonomy_version": "macro_v1",
                }
            )
        rows[0].update(score=0.5, assessment="positive", confidence="high", evidence_count=2)
        breadth = MODULE.build_daily_breadth(rows)[0]
        self.assertEqual(breadth["mean_score"], 0.5)
        self.assertEqual(breadth["observed_themes"], 1)
        self.assertEqual(breadth["coverage_pct"], 10.0)

    def test_read_only_connection_rejects_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.db"
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE sample (id INTEGER)")
            con.commit()
            con.close()
            read_only = MODULE.connect_read_only(path)
            with self.assertRaises(sqlite3.OperationalError):
                read_only.execute("INSERT INTO sample VALUES (1)")
            read_only.close()


if __name__ == "__main__":
    unittest.main()
