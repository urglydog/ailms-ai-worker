"""Job thứ 2 trong cùng tiến trình Celery (event loop mới) không được lỗi Lock (job 32)."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.providers import azure_tts


def test_token_lock_works_across_event_loops():
    async def issue():
        await asyncio.sleep(0.01)
        return "tok"

    async def contend():
        azure_tts._token = None
        with patch("app.providers.azure_tts._issue_token", AsyncMock(side_effect=issue)):
            return await asyncio.gather(*(azure_tts._get_token() for _ in range(5)))

    assert asyncio.run(contend()) == ["tok"] * 5
    assert asyncio.run(contend()) == ["tok"] * 5     # loop moi, truoc day loi "different event loop"
