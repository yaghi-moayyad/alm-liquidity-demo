import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import etl  # noqa: E402


class TextToSqliteEtlTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.schema = self.root / "schema.json"
        self.input_dir = self.root / "input"
        self.input_dir.mkdir()
        self.database = self.root / "source.sqlite3"
        self.schema.write_text(json.dumps({"tables": [{
            "table_name": "DemoContract",
            "source_file": "DemoContract.Import",
            "columns": [
                {"name": "BALANCESHEETDATE", "type": "integer", "nullable": False},
                {"name": "CONTRACTREFERENCE", "type": "string", "nullable": False},
                {"name": "BALANCE", "type": "decimal", "nullable": False},
                {"name": "AUTOMATICCANCELLATION", "type": "boolean", "nullable": False},
            ],
        }]}), encoding="utf-8")

    def tearDown(self):
        self.workspace.cleanup()

    def run_load(self, *extra):
        return etl.main_with_args([
            "load", "--input-dir", str(self.input_dir), "--database", str(self.database),
            "--schema", str(self.schema), "--entity", "jordan", "--as-of-date", "2026-09-21", *extra,
        ])

    def test_loads_valid_rows_and_rejects_invalid_ones(self):
        (self.input_dir / "DemoContract").write_text(
            "BALANCESHEETDATE|CONTRACTREFERENCE|BALANCE|AUTOMATICCANCELLATION\n"
            "20260921|ABC-1|123456789.123|false\n"
            "20260921|ABC-2|not-a-number|true\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_load(), 0)
        with sqlite3.connect(self.database) as connection:
            value = connection.execute('SELECT BALANCE, AUTOMATICCANCELLATION FROM "DemoContract"').fetchone()
            self.assertEqual(value, ("123456789.123", 0))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM etl_rejections").fetchone()[0], 1)

    def test_replace_date_replaces_the_previous_snapshot(self):
        (self.input_dir / "DemoContract").write_text(
            "BALANCESHEETDATE|CONTRACTREFERENCE|BALANCE|AUTOMATICCANCELLATION\n20260921|ABC-1|10|0\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_load(), 0)
        (self.input_dir / "DemoContract").write_text(
            "BALANCESHEETDATE|CONTRACTREFERENCE|BALANCE|AUTOMATICCANCELLATION\n20260921|ABC-1|20|0\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_load(), 0)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM "DemoContract"').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT BALANCE FROM "DemoContract"').fetchone()[0], "20")

    def test_load_uses_only_rows_for_the_requested_balance_sheet_date(self):
        (self.input_dir / "DemoContract").write_text(
            "BALANCESHEETDATE|CONTRACTREFERENCE|BALANCE|AUTOMATICCANCELLATION\n"
            "20251007|OLD-1|10|0\n"
            "20260921|NEW-1|20|0\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_load(), 0)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT CONTRACTREFERENCE FROM "DemoContract"').fetchone()[0], "NEW-1")

    def test_exact_duplicates_are_excluded_and_audited(self):
        (self.input_dir / "DemoContract").write_text(
            "BALANCESHEETDATE|CONTRACTREFERENCE|BALANCE|AUTOMATICCANCELLATION\n"
            "20260921|ABC-1|10|0\n"
            "20260921|ABC-1|10|0\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_load(), 0)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM "DemoContract"').fetchone()[0], 1)
            audit = connection.execute(
                "SELECT source_row, retained_source_row FROM etl_exact_duplicates"
            ).fetchone()
            self.assertEqual(audit, (3, 2))

    def test_file_name_can_include_the_bank_import_suffix(self):
        (self.input_dir / "DemoContract.DemoImport").write_text(
            "BALANCESHEETDATE|CONTRACTREFERENCE|BALANCE|AUTOMATICCANCELLATION\n20260921|ABC-1|10|0\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_load(), 0)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM "DemoContract"').fetchone()[0], 1)

    def test_known_account_business_key_keeps_first_row_and_audits_later_copy(self):
        schema = self.root / "account-schema.json"
        schema.write_text(json.dumps({"tables": [{
            "table_name": "EquationJordanAccountContract",
            "columns": [
                {"name": "BALANCESHEETDATE", "type": "integer", "nullable": False},
                {"name": "CONTRACTREFERENCE", "type": "string", "nullable": False},
                {"name": "ACCOUNTREFERENCE", "type": "string", "nullable": False},
                {"name": "AB_CODE", "type": "string", "nullable": False},
                {"name": "AB_SOURCESYSTEM", "type": "string", "nullable": False},
                {"name": "CURRENCY", "type": "string", "nullable": False},
                {"name": "BALANCE", "type": "decimal", "nullable": False},
            ],
        }]}), encoding="utf-8")
        (self.input_dir / "EquationJordanAccountContract.AccountImport").write_text(
            "BALANCESHEETDATE|CONTRACTREFERENCE|ACCOUNTREFERENCE|AB_CODE|AB_SOURCESYSTEM|CURRENCY|BALANCE\n"
            "20260921|REF-1|60609|UB|EquationDepositAccount|JOD|10\n"
            "20260921|REF-1|60609|UB|EquationDepositAccount|JOD|11\n",
            encoding="utf-8",
        )
        self.assertEqual(etl.main_with_args([
            "load", "--input-dir", str(self.input_dir), "--database", str(self.database),
            "--schema", str(schema), "--entity", "jordan", "--as-of-date", "2026-09-21",
        ]), 0)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute('SELECT BALANCE FROM "EquationJordanAccountContract"').fetchone()[0], "10")
            reason=connection.execute('SELECT reason FROM etl_exact_duplicates').fetchone()[0]
            self.assertIn("five-field account business key", reason)


if __name__ == "__main__":
    unittest.main()
