"""Tests for the shared general message catalog loader."""

import unittest

from domain.workflow.general_messages import load_general_messages


class GeneralMessagesLoaderTests(unittest.TestCase):
    def test_loads_new_formal_limit_messages(self) -> None:
        messages = load_general_messages()

        self.assertTrue(messages.daily_session_limit_message.strip())
        self.assertTrue(messages.repeat_flow_recheck_exhausted_message.strip())

    def test_existing_repeated_flow_messages_are_preserved(self) -> None:
        messages = load_general_messages()

        self.assertIn("{last_flow_label}", messages.repeated_flow_warning_template)
        self.assertTrue(messages.repeated_flow_continue_message.strip())
        self.assertTrue(messages.repeated_flow_decline_message.strip())


if __name__ == "__main__":
    unittest.main()
