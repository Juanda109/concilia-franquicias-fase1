"""Unit tests for the maintenance archive HTTP client."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.persistence import maintenance_client
from infrastructure.persistence.maintenance_client import (
    _resolve_archive_url,
    trigger_archive_conversation,
)


class ResolveArchiveUrlTests(unittest.TestCase):
    def test_templated_url_is_filled_with_conversation_id(self) -> None:
        url = _resolve_archive_url(
            base_url="http://maint:8001/end/{conversation_id}",
            conversation_id="111_20260618",
        )
        self.assertEqual(url, "http://maint:8001/end/111_20260618")

    def test_plain_base_url_appends_end_path(self) -> None:
        url = _resolve_archive_url(
            base_url="http://maint:8001/",
            conversation_id="111_20260618",
        )
        self.assertEqual(url, "http://maint:8001/end/111_20260618")


class TriggerArchiveConversationTests(unittest.IsolatedAsyncioTestCase):
    def _patched_client(self, post_mock: AsyncMock):
        fake_client = MagicMock()
        fake_client.post = post_mock
        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=fake_client)
        async_cm.__aexit__ = AsyncMock(return_value=False)
        return patch.object(
            maintenance_client.httpx, "AsyncClient", return_value=async_cm
        )

    async def test_posts_to_resolved_maintenance_url(self) -> None:
        post_mock = AsyncMock(return_value=MagicMock(status_code=200))

        with self._patched_client(post_mock):
            await trigger_archive_conversation(
                base_url="http://maint:8001/end/{conversation_id}",
                conversation_id="111_20260618",
            )

        post_mock.assert_awaited_once()
        called_url = post_mock.await_args.args[0]
        self.assertEqual(called_url, "http://maint:8001/end/111_20260618")

    async def test_errors_are_swallowed(self) -> None:
        post_mock = AsyncMock(side_effect=RuntimeError("boom"))

        with self._patched_client(post_mock):
            # Must not raise.
            await trigger_archive_conversation(
                base_url="http://maint:8001",
                conversation_id="111_20260618",
            )

        post_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
