"""Guard: E2E_DEBUG_TRACE must be read from the .env constants (load_env_constants),
NOT only from os.getenv. The configmap mounts .env as a FILE, so os.getenv alone
does not see it — this was the bug that silenced all DEBUG traces in-cluster.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from application.customer import consultar_service


class E2EFlagFromEnvFileTests(unittest.TestCase):
    def test_reads_true_from_env_constants_without_os_getenv(self) -> None:
        os.environ.pop("E2E_DEBUG_TRACE", None)  # no real env var
        with patch.object(
            consultar_service, "load_env_constants", return_value={"E2E_DEBUG_TRACE": "true"}
        ):
            self.assertTrue(consultar_service._e2e_debug_enabled())

    def test_reads_false_from_env_constants(self) -> None:
        os.environ.pop("E2E_DEBUG_TRACE", None)
        with patch.object(
            consultar_service, "load_env_constants", return_value={"E2E_DEBUG_TRACE": "false"}
        ):
            self.assertFalse(consultar_service._e2e_debug_enabled())

    def test_missing_defaults_false(self) -> None:
        os.environ.pop("E2E_DEBUG_TRACE", None)
        with patch.object(consultar_service, "load_env_constants", return_value={}):
            self.assertFalse(consultar_service._e2e_debug_enabled())


if __name__ == "__main__":
    unittest.main()
