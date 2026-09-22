import sqlite3
import sys
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_to_alm as publisher  # noqa: E402


class PublisherMappingTests(unittest.TestCase):
    def row(self, **values):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        columns = ", ".join(f'"{name}" TEXT' for name in values)
        connection.execute(f"CREATE TABLE item ({columns})")
        connection.execute(
            f"INSERT INTO item ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            list(values.values()),
        )
        return connection.execute("SELECT * FROM item").fetchone()

    def test_maps_open_demand_deposit_without_inventing_dates(self):
        row = self.row(CONTRACTREFERENCE="12345", BALANCE="1000.125", CURRENCY="JOD", PRODUCTTYPE="Current", _etl_source_row="2")
        result = publisher.map_contract(row, {
            "name": "Retail current", "id_prefix": "EQ-AC", "product": "demand_deposit",
            "principal_column": "BALANCE", "currency_column": "CURRENCY",
            "liquidity_group": "Retail call", "liquidity_product_column": "PRODUCTTYPE",
        }, date(2026, 9, 21))
        self.assertEqual(result["contract_id"], "EQ-AC-12345")
        self.assertEqual(result["principal"], "1000.125")
        self.assertNotIn("maturity", result)

    def test_maps_dated_loan_with_confirmed_terms(self):
        row = self.row(
            CONTRACTREFERENCE="LN-9", PRINCIPAL="100000", CURRENCY="JOD", PRODUCTTYPE="Personal",
            ORIGINDATE="20250101", INTERESTBREAKINGDATE="20261001", MATURITYDATE="20280101",
            FIXEDRATE="6.5", INTERESTRATETYPE="Fixed", _etl_source_row="2",
        )
        result = publisher.map_contract(row, {
            "name": "Loans", "id_prefix": "EQ-LN", "product": "loan", "principal_column": "PRINCIPAL",
            "currency_column": "CURRENCY", "liquidity_product_column": "PRODUCTTYPE", "liquidity_group": "Retail term",
            "annual_rate_column": "FIXEDRATE", "annual_rate_scale": "percent", "rate_type_column": "INTERESTRATETYPE",
            "frequency_months": 3, "repayment": "bullet", "accrual_start_column": "ORIGINDATE",
            "next_payment_column": "INTERESTBREAKINGDATE", "maturity_column": "MATURITYDATE",
        }, date(2026, 9, 21))
        self.assertEqual(result["annual_rate"], "0.065")
        self.assertEqual(result["next_payment"], "2026-10-01")

    def test_rejects_dated_product_without_a_payment_date(self):
        row = self.row(CONTRACTREFERENCE="LN-9", PRINCIPAL="100", CURRENCY="JOD", _etl_source_row="2")
        with self.assertRaisesRegex(publisher.PublishError, "next_payment_column"):
            publisher.map_contract(row, {
                "id_prefix": "EQ-LN", "product": "loan", "principal_column": "PRINCIPAL",
                "currency_column": "CURRENCY", "accrual_start_column": "ORIGINDATE", "maturity_column": "MATURITYDATE",
            }, date(2026, 9, 21))

    def test_preserves_invalid_coupon_dates_for_calculation_time_resolution(self):
        row = self.row(
            CONTRACTREFERENCE="LN-LONG", PRINCIPAL="100000", CURRENCY="JOD", PRODUCTTYPE="Corporate",
            ORIGINDATE="20200101", NEXTINTERESTPAYMENTDATE="20261001", MATURITYDATE="20280101",
            FIXEDRATE="6.5", _etl_source_row="2",
        )
        result = publisher.map_contract(row, {
            "name": "Legacy auto mapping", "id_prefix": "EQ-LN", "product": "loan", "principal_column": "PRINCIPAL",
            "currency_column": "CURRENCY", "liquidity_product_column": "PRODUCTTYPE", "liquidity_group": "Loans",
            "annual_rate_column": "FIXEDRATE", "annual_rate_scale": "percent", "frequency_months": 3,
            "accrual_start_column": "ORIGINDATE", "next_payment_column": "MATURITYDATE", "maturity_column": "MATURITYDATE",
        }, date(2026, 9, 21))
        self.assertEqual(result["source_date_candidates"]["NEXTINTERESTPAYMENTDATE"], "2026-10-01")
        self.assertIn("first accrual period exceeds 370 days", result["data_quality"]["issues"])

    def test_dry_run_reads_completed_stage_batch_and_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_db = root / "source.sqlite3"
            mapping_file = root / "mapping.json"
            report_file = root / "report.json"
            with sqlite3.connect(source_db) as connection:
                connection.execute("CREATE TABLE etl_batches (batch_id TEXT, entity_code TEXT, as_of_date TEXT, status TEXT, finished_at TEXT)")
                connection.execute("INSERT INTO etl_batches VALUES ('batch-1', 'jordan', '2026-09-21', 'completed', '2026-09-21T00:00:00Z')")
                connection.execute('''CREATE TABLE "DemoContract" (
                    CONTRACTREFERENCE TEXT, BALANCE TEXT, CURRENCY TEXT, PRODUCTTYPE TEXT,
                    _etl_batch_id TEXT, _etl_source_row INTEGER)''')
                connection.execute('INSERT INTO "DemoContract" VALUES ("A-1", "100", "JOD", "Current", "batch-1", 2)')
            mapping_file.write_text(json.dumps({
                "source_entity": "jordan", "entity_slug": "jordan-bank-demo", "as_of_date": "2026-09-21",
                "portfolio": {"rules": [{"source_table": "DemoContract", "id_prefix": "D", "product": "demand_deposit", "principal_column": "BALANCE", "currency_column": "CURRENCY", "liquidity_product_column": "PRODUCTTYPE"}]},
                "regulatory": {"enabled": False, "lcr_rules": []},
            }))
            code = publisher.main([
                "publish", "--source-database", str(source_db), "--mapping", str(mapping_file),
                "--django-project", str(root), "--app-database", str(root / "unused.sqlite3"),
                "--dry-run", "--report", str(report_file),
            ])
            self.assertEqual(code, 0)
            report = json.loads(report_file.read_text())
            self.assertEqual(report["mapped_portfolio_contracts"], 1)
            self.assertEqual(report["status"], "dry_run")


if __name__ == "__main__":
    unittest.main()
