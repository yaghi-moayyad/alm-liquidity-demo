import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_pipeline  # noqa: E402


class PipelineTests(unittest.TestCase):
    def test_validate_only_runs_staging_inventory_and_mapping_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_files = root / "input"
            source_files.mkdir()
            schema = root / "schema.json"
            mapping = root / "mapping.json"
            source_database = root / "stage.sqlite3"
            status = root / "status.json"
            inventory = root / "inventory.json"
            report = root / "publish.json"
            schema.write_text(json.dumps({"tables": [{
                "table_name": "DemoContract", "source_file": "Demo", "columns": [
                    {"name": "BALANCESHEETDATE", "type": "integer", "nullable": False},
                    {"name": "CONTRACTREFERENCE", "type": "string", "nullable": False},
                    {"name": "BALANCE", "type": "decimal", "nullable": False},
                    {"name": "CURRENCY", "type": "string", "nullable": False},
                    {"name": "PRODUCTTYPE", "type": "string", "nullable": False},
                ],
            }]}))
            (source_files / "DemoContract").write_text(
                "BALANCESHEETDATE|CONTRACTREFERENCE|BALANCE|CURRENCY|PRODUCTTYPE\n20260921|A-1|100|JOD|Current\n"
            )
            mapping.write_text(json.dumps({
                "source_entity": "jordan", "entity_slug": "jordan-bank-demo", "as_of_date": "2026-09-21",
                "portfolio": {"rules": [{"source_table": "DemoContract", "id_prefix": "D", "product": "demand_deposit", "principal_column": "BALANCE", "currency_column": "CURRENCY", "liquidity_product_column": "PRODUCTTYPE"}]},
                "regulatory": {"enabled": False, "lcr_rules": []},
            }))
            result = run_pipeline.main([
                "--input-dir", str(source_files), "--source-database", str(source_database), "--mapping", str(mapping),
                "--django-project", str(root / "not-needed-in-validate-only"), "--app-database", str(root / "not-needed.sqlite3"),
                "--schema", str(schema), "--as-of-date", "2026-09-21", "--validate-only",
                "--status-file", str(status), "--inventory-file", str(inventory), "--publish-report", str(report),
            ])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(status.read_text())["state"], "completed_validation")
            self.assertEqual(json.loads(report.read_text())["mapped_portfolio_contracts"], 1)
            self.assertIn("DemoContract", json.loads(inventory.read_text())["tables"])


if __name__ == "__main__":
    unittest.main()
