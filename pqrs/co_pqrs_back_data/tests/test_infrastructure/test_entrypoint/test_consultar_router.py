"""Regression tests for the back-data routes that remain after TXNR decoupling."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from infrastructure.entrypoint.api.router.v0 import consultar_router as router


class CustomerNameRouteTests(unittest.TestCase):
    def test_returns_the_customer_name_after_a_successful_lookup(self) -> None:
        with mock.patch.object(router, "get_customer_display_name", return_value="Ana"):
            result = asyncio.run(
                router.customer_name(
                    customer_id="1010223694",
                    logger=mock.Mock(),
                    identity_repository=mock.Mock(),
                )
            )

        self.assertEqual(
            result,
            {"customer_id": "1010223694", "given_name": "Ana", "found": True},
        )

    def test_fails_open_when_the_lookup_raises(self) -> None:
        with (
            mock.patch.object(
                router, "get_customer_display_name", side_effect=RuntimeError("db down")
            ),
            mock.patch.object(router, "schedule_error_report") as report,
        ):
            result = asyncio.run(
                router.customer_name(
                    customer_id="1010223694",
                    logger=mock.Mock(),
                    identity_repository=mock.Mock(),
                )
            )

        self.assertEqual(
            result,
            {"customer_id": "1010223694", "given_name": "", "found": False},
        )
        report.assert_called_once()
