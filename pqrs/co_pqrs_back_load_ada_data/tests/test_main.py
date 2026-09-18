"""Unit tests for load_ada_data pure helpers (no DB required)."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


class QuotingTests(unittest.TestCase):
    def test_quote_ident_basic(self) -> None:
        self.assertEqual(main.quote_ident("ada_info_detail"), '"ada_info_detail"')

    def test_quote_ident_escapes_double_quotes(self) -> None:
        self.assertEqual(main.quote_ident('a"b'), '"a""b"')

    def test_index_name(self) -> None:
        self.assertEqual(
            main.index_name("ada_info_detail", "customer_id"),
            "idx_ada_info_detail_customer_id",
        )


class SqlBuilderTests(unittest.TestCase):
    def test_create_table_unlogged(self) -> None:
        sql = main.build_create_table_sql("t", unlogged=True, if_not_exists=False)
        self.assertTrue(sql.startswith('CREATE UNLOGGED TABLE "t"'))
        self.assertIn("customer_id TEXT", sql)
        self.assertIn("personal_id TEXT", sql)

    def test_create_table_logged(self) -> None:
        sql = main.build_create_table_sql("t", unlogged=False, if_not_exists=False)
        self.assertTrue(sql.startswith('CREATE TABLE "t"'))
        self.assertNotIn("UNLOGGED", sql)

    def test_copy_sql(self) -> None:
        sql = main.build_copy_sql("t", ("customer_id", "personal_id"))
        self.assertIn('COPY "t" ("customer_id", "personal_id") FROM STDIN', sql)
        self.assertIn("FORMAT csv", sql)
        self.assertIn("NULL ''", sql)

    def test_create_index_sql(self) -> None:
        sql = main.build_create_index_sql("idx_t_customer_id", "t", "customer_id")
        self.assertEqual(sql, 'CREATE INDEX "idx_t_customer_id" ON "t" ("customer_id")')

    def test_create_expr_index_sql_matches_repo_predicate(self) -> None:
        # The expression index must mirror the identity-lookup predicate exactly.
        self.assertEqual(main.CUSTOMER_ID_NORM_EXPR, "NULLIF(LTRIM(customer_id, '0'), '')")
        sql = main.build_create_expr_index_sql(
            "idx_ada_info_detail_customer_id_norm", "ada_info_detail", main.CUSTOMER_ID_NORM_EXPR
        )
        self.assertEqual(
            sql,
            'CREATE INDEX "idx_ada_info_detail_customer_id_norm" ON "ada_info_detail" '
            "((NULLIF(LTRIM(customer_id, '0'), '')))",
        )

    def test_session_tuning_statements(self) -> None:
        settings = _make_settings()
        stmts = main.build_session_tuning_statements(settings)
        self.assertIn("SET synchronous_commit = off", stmts)
        self.assertIn("SET work_mem = '256MB'", stmts)
        self.assertIn("SET maintenance_work_mem = '1GB'", stmts)
        self.assertIn("SET max_parallel_maintenance_workers = 4", stmts)
        self.assertIn("SET statement_timeout = 0", stmts)

    def test_index_columns_kept(self) -> None:
        # Both point-lookup indexes must be preserved.
        self.assertIn("customer_id", main.INDEX_COLUMNS)
        self.assertIn("personal_id", main.INDEX_COLUMNS)


class SettingsValidationTests(unittest.TestCase):
    def test_validate_mem_ok(self) -> None:
        self.assertEqual(main.validate_mem("X", "1GB"), "1GB")
        self.assertEqual(main.validate_mem("X", "512MB"), "512MB")

    def test_validate_mem_rejects_injection(self) -> None:
        with self.assertRaises(ValueError):
            main.validate_mem("X", "1GB; DROP TABLE t")

    def test_parse_bool_env(self) -> None:
        os.environ["_T_BOOL"] = "false"
        try:
            self.assertFalse(main.parse_bool_env("_T_BOOL", default=True))
        finally:
            os.environ.pop("_T_BOOL", None)
        self.assertTrue(main.parse_bool_env("_T_MISSING", default=True))

    def test_expected_folder_name_uses_yesterday(self) -> None:
        settings = _make_settings()
        name = main.expected_folder_name(settings, now=datetime(2026, 7, 15, 2, 0, 0))
        self.assertEqual(name, "pqrs_ada_data_20260714")


def _make_settings() -> "main.Settings":
    return main.Settings(
        db_host="h",
        db_port=5432,
        db_name="d",
        db_user="u",
        db_password="p",
        process_path=Path("/mnt/ada_data"),
        folder_prefix="pqrs_ada_data_",
        target_table="ada_info_detail",
        parquet_batch_size=100_000,
        unlogged=True,
        work_mem="256MB",
        maintenance_work_mem="1GB",
        max_parallel_maintenance_workers=4,
    )


if __name__ == "__main__":
    unittest.main()
