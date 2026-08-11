"""F5.3 — sự kiện tiến độ CẤP-JOB (không có `chunkIndex`), phân biệt với sự kiện cấp-chunk đã
có từ F5.2. FE cần biết CHÍNH XÁC lúc job kết thúc (COMPLETED/FAILED/SKIPPED), không chỉ dựa
vào chunk cuối — vì còn phải chờ FFmpeg concat + upload B2 + gọi callback `finish_*` xong.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.services import dubbing_service
from app.services.dubbing_service import SkippedPipelineError


async def test_skipped_pipeline_publishes_job_level_skipped_event(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "temp_dir", str(tmp_path))

    ctx = SimpleNamespace(
        video_source="UPLOAD", video_url="https://example.test/v.mp4",
        duration_sec=600, source_transcript_available=False,
    )
    finish_skipped_mock = AsyncMock()
    publish_progress_mock = AsyncMock()

    with patch("app.http.backend_client.get_context", AsyncMock(return_value=ctx)), \
         patch("app.media.extract_audio_from_url", AsyncMock()), \
         patch("app.http.backend_client.start_job", AsyncMock()), \
         patch("app.services.dubbing_service._process_chunk_with_retry",
               AsyncMock(side_effect=SkippedPipelineError("thoai < 10% - BR-DUB-10"))), \
         patch("app.http.backend_client.finish_skipped", finish_skipped_mock), \
         patch("app.redis_client.publish_progress", publish_progress_mock):
        result = await dubbing_service.run_dubbing_pipeline(
            job_id=1, lesson_id=21, video_url="https://example.test/v.mp4", target_language="en-US",
        )

    assert result == {"status": "SKIPPED", "jobId": 1}
    finish_skipped_mock.assert_awaited_once()
    publish_progress_mock.assert_awaited_once_with(1, 21, status="SKIPPED")
    # Su kien cap-job KHONG duoc co chunkIndex (FE dung dieu nay de phan biet 2 loai su kien)
    assert "chunkIndex" not in publish_progress_mock.await_args.kwargs


async def test_unexpected_failure_publishes_job_level_failed_event(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "temp_dir", str(tmp_path))

    publish_progress_mock = AsyncMock()

    with patch("app.http.backend_client.get_context",
               AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("app.http.backend_client.finish_failed", AsyncMock()), \
         patch("app.redis_client.publish_progress", publish_progress_mock):
        try:
            await dubbing_service.run_dubbing_pipeline(
                job_id=2, lesson_id=22, video_url="https://example.test/v.mp4", target_language="en-US",
            )
        except RuntimeError:
            pass

    publish_progress_mock.assert_awaited_once_with(2, 22, status="FAILED")
