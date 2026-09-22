import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_demo  # noqa: E402


class SimpleDemoRunnerTests(unittest.TestCase):
    def test_automatic_mapping_uses_only_safe_table_name_classifications(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "bank_text_to_sqlite_etl"
            package.mkdir()
            schema = {"tables": [{
                "table_name": "DemoContract", "source_file": "Demo", "columns": [
                    {"name": "BALANCESHEETDATE", "type": "integer", "nullable": False},
                    {"name": "CONTRACTREFERENCE", "type": "string", "nullable": False},
                    {"name": "BALANCE", "type": "decimal", "nullable": False},
                ],
            }]}
            (package / "schema_horizontal.json").write_text(json.dumps(schema))
            mapping = run_demo.automatic_mapping(package / "schema_horizontal.json")
            self.assertEqual(mapping["version"], "demo-auto-1.0")
            self.assertEqual(mapping["portfolio"]["rules"], [])
            self.assertFalse(mapping["regulatory"]["enabled"])


if __name__ == "__main__":
    unittest.main()
