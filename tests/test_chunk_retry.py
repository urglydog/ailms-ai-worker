"""BR-CHUNK-04 — retry tối đa MAX_RETRY lần với exponential backoff cho MỘT chunk;
`SKIPPED` (BR-DUB-10) tuyệt đối KHÔNG được đưa vào vòng retry này.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.dubbing_service import ChunkPlan, SkippedPipelineError, _process_chunk_with_retry


async def test_gives_up_after_max_retry_attempts(monkeypatch):
    monkeypatch.setattr(settings, "max_retry", 3)
    sleep_mock = AsyncMock()
    chunk_once_mock = AsyncMock(side_effect=RuntimeError("Groq tam thoi loi"))

    with patch("app.services.dubbing_service._process_chunk_once", chunk_once_mock), \
         patch("asyncio.sleep", sleep_mock):
        with pytest.raises(RuntimeError, match="Groq tam thoi loi"):
            await _process_chunk_with_retry(
                job_id=1, ctx=object(), chunk=ChunkPlan(0, 0, 600),
                source_audio="src.wav", work_dir="/tmp/x", reuse_source=False, next_seq=1,
            )

    assert chunk_once_mock.await_count == settings.max_retry == 3
    assert sleep_mock.await_count == settings.max_retry - 1  # khong sleep sau lan cuoi cung (da bo cuoc)


async def test_succeeds_on_second_attempt_without_exhausting_retries(monkeypatch):
    monkeypatch.setattr(settings, "max_retry", 3)
    sleep_mock = AsyncMock()
    chunk_once_mock = AsyncMock(side_effect=[RuntimeError("loi tam thoi lan 1"), ("chunk_0.mp3", 5)])

    with patch("app.services.dubbing_service._process_chunk_once", chunk_once_mock), \
         patch("asyncio.sleep", sleep_mock):
        result = await _process_chunk_with_retry(
            job_id=1, ctx=object(), chunk=ChunkPlan(0, 0, 600),
            source_audio="src.wav", work_dir="/tmp/x", reuse_source=False, next_seq=1,
        )

    assert result == ("chunk_0.mp3", 5)
    assert chunk_once_mock.await_count == 2
    assert sleep_mock.await_count == 1


async def test_skipped_pipeline_error_bypasses_retry_entirely():
    """BR-DUB-10: ký âm rỗng/thoại quá ít KHÔNG được retry, phải bubble lên ngay lần đầu."""
    chunk_once_mock = AsyncMock(side_effect=SkippedPipelineError("thoai < 10%"))

    with patch("app.services.dubbing_service._process_chunk_once", chunk_once_mock):
        with pytest.raises(SkippedPipelineError):
            await _process_chunk_with_retry(
                job_id=1, ctx=object(), chunk=ChunkPlan(0, 0, 600),
                source_audio="src.wav", work_dir="/tmp/x", reuse_source=False, next_seq=1,
            )

    assert chunk_once_mock.await_count == 1  # khong duoc thu lai
