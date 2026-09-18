"""Unit tests for environment configuration loaders."""

import os
import unittest
from unittest.mock import patch

from infrastructure.core.config import (
    load_end_conversation_callback_url,
    load_max_daily_category_interactions,
    load_max_daily_sessions,
    load_max_repeat_rechecks,
)


class MaxDailySessionsConfigTests(unittest.TestCase):
    def test_defaults_to_three_when_unset(self) -> None:
        with patch.dict(os.environ, {"PLACEHOLDER": "1"}, clear=True):
            self.assertEqual(load_max_daily_sessions(env_path="does-not-exist.env"), 3)

    def test_reads_override_from_environment(self) -> None:
        with patch.dict(os.environ, {"MAX_DAILY_SESSIONS": "5"}, clear=True):
            self.assertEqual(load_max_daily_sessions(env_path="does-not-exist.env"), 5)

    def test_invalid_value_falls_back_to_default(self) -> None:
        with patch.dict(os.environ, {"MAX_DAILY_SESSIONS": "abc"}, clear=True):
            self.assertEqual(load_max_daily_sessions(env_path="does-not-exist.env"), 3)

    def test_non_positive_value_falls_back_to_default(self) -> None:
        with patch.dict(os.environ, {"MAX_DAILY_SESSIONS": "0"}, clear=True):
            self.assertEqual(load_max_daily_sessions(env_path="does-not-exist.env"), 3)


class MaxDailyCategoryInteractionsConfigTests(unittest.TestCase):
    def test_defaults_to_three_when_unset(self) -> None:
        with patch.dict(os.environ, {"PLACEHOLDER": "1"}, clear=True):
            self.assertEqual(
                load_max_daily_category_interactions(env_path="does-not-exist.env"), 3
            )

    def test_reads_override_from_environment(self) -> None:
        with patch.dict(
            os.environ, {"MAX_DAILY_CATEGORY_INTERACTIONS": "4"}, clear=True
        ):
            self.assertEqual(
                load_max_daily_category_interactions(env_path="does-not-exist.env"), 4
            )

    def test_invalid_value_falls_back_to_default(self) -> None:
        with patch.dict(
            os.environ, {"MAX_DAILY_CATEGORY_INTERACTIONS": "abc"}, clear=True
        ):
            self.assertEqual(
                load_max_daily_category_interactions(env_path="does-not-exist.env"), 3
            )


class MaxRepeatRechecksConfigTests(unittest.TestCase):
    def test_defaults_to_three_when_unset(self) -> None:
        with patch.dict(os.environ, {"PLACEHOLDER": "1"}, clear=True):
            self.assertEqual(load_max_repeat_rechecks(env_path="does-not-exist.env"), 3)

    def test_reads_override_from_environment(self) -> None:
        with patch.dict(os.environ, {"MAX_REPEAT_RECHECKS": "2"}, clear=True):
            self.assertEqual(load_max_repeat_rechecks(env_path="does-not-exist.env"), 2)

    def test_non_positive_value_falls_back_to_default(self) -> None:
        with patch.dict(os.environ, {"MAX_REPEAT_RECHECKS": "0"}, clear=True):
            self.assertEqual(load_max_repeat_rechecks(env_path="does-not-exist.env"), 3)


class EndConversationCallbackUrlConfigTests(unittest.TestCase):
    def test_returns_none_when_unset(self) -> None:
        with patch.dict(os.environ, {"PLACEHOLDER": "1"}, clear=True):
            self.assertIsNone(
                load_end_conversation_callback_url(env_path="does-not-exist.env")
            )

    def test_reads_maintenance_url_from_environment(self) -> None:
        url = "http://co-pqrs-back-maintenance.pqr-genai-dev:8001/end/{conversation_id}"
        with patch.dict(
            os.environ, {"END_CONVERSATION_CALLBACK_URL": url}, clear=True
        ):
            self.assertEqual(
                load_end_conversation_callback_url(env_path="does-not-exist.env"),
                url,
            )


if __name__ == "__main__":
    unittest.main()
