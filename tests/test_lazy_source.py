"""Tối ưu B: chỉ tải audio gốc khi cần; tối ưu C: index Gia sư AI chạy nền."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app import source_audio
from app.config import settings
from app.services import dubbing_service


async def test_ensure_downloads_once_even_with_concurrent_callers(tmp_path):
    calls = []

    async def download(path):
        calls.append(path)
        await asyncio.sleep(0.01)
        path.write_bytes(b"wav")

    p = tmp_path / "source.wav"
    source_audio.register(p, download)
    try:
        await asyncio.gather(*(source_audio.ensure(p) for _ in range(5)))
        assert len(calls) == 1 and source_audio.was_downloaded(p)
    finally:
        source_audio.unregister(p)


async def test_download_error_is_source_unavailable(tmp_path):
    p = tmp_path / "source.wav"
    source_audio.register(p, AsyncMock(side_effect=RuntimeError("yt-dlp bi chan")))
    try:
        with pytest.raises(source_audio.SourceUnavailableError):
            await source_audio.ensure(p)
    finally:
        source_audio.unregister(p)


def _ctx(transcript=True):
    return SimpleNamespace(
        video_source="YOUTUBE", video_url="https://youtu.be/x", duration_sec=300,
        source_transcript_available=transcript, lesson_id=21, target_language="vi-VN",
    )


async def _run(tmp_path, monkeypatch, ctx, chunk_side_effect):
    monkeypatch.setattr(settings, "temp_dir", str(tmp_path))
    monkeypatch.setattr(settings, "bgm_separation", "")
    download = AsyncMock(side_effect=lambda url, path: open(path, "wb").write(b"wav"))
    with patch("app.http.backend_client.get_context", AsyncMock(return_value=ctx)), \
         patch("app.media.download_youtube_audio", download), \
         patch("app.http.backend_client.start_job", AsyncMock()), \
         patch("app.services.dubbing_service._prepare_chunk_with_retry", AsyncMock(return_value=SimpleNamespace(consumed=0))), \
         patch("app.services.dubbing_service._finish_chunk_with_retry", AsyncMock(side_effect=chunk_side_effect)), \
         patch("app.http.backend_client.finish_completed", AsyncMock()), \
         patch("app.http.backend_client.upsert_chunk_failed", AsyncMock()), \
         patch("app.http.backend_client.finish_failed", AsyncMock()), \
         patch("app.redis_client.publish_progress", AsyncMock()), \
         patch("app.audio_utils.probe_audio", AsyncMock(return_value=(300.0, 44100))), \
         patch("app.audio_utils.extract_range", AsyncMock(side_effect=lambda src, a, b, out: open(out, "wb").write(b"x"))):
        result = await dubbing_service.run_dubbing_pipeline(
            job_id=9, lesson_id=21, video_url="https://youtu.be/x", target_language="vi-VN",
        )
    return result, download


async def test_second_language_job_does_not_download_source(tmp_path, monkeypatch):
    chunk_file = tmp_path / "c.mp3"
    chunk_file.write_bytes(b"a")
    result, download = await _run(tmp_path, monkeypatch, _ctx(transcript=True), [(chunk_file, 0)])
    assert result["status"] == "COMPLETED"
    download.assert_not_awaited()                     # da co ban ky am, nhac nen tat -> khong tai


async def test_first_job_downloads_source_upfront(tmp_path, monkeypatch):
    chunk_file = tmp_path / "c.mp3"
    chunk_file.write_bytes(b"a")
    _result, download = await _run(tmp_path, monkeypatch, _ctx(transcript=False), [(chunk_file, 5)])
    download.assert_awaited_once()


async def test_failed_chunk_downloads_source_lazily_for_fallback(tmp_path, monkeypatch):
    result, download = await _run(tmp_path, monkeypatch, _ctx(transcript=True), RuntimeError("tts loi"))
    assert result["reason"] == "ALL_CHUNKS_FALLBACK"
    download.assert_awaited_once()                    # chi tai khi can giu audio goc cho chunk loi


async def test_tutor_indexing_runs_in_background_and_is_awaited(monkeypatch):
    gate = asyncio.Event()
    done = []

    async def slow_index(lesson_id, lang, segments):
        await gate.wait()
        done.append(lesson_id)

    with patch("app.services.tutor_indexing.index_segments", AsyncMock(side_effect=slow_index)):
        task = asyncio.create_task(dubbing_service._index_for_tutor(21, "en", []))
        dubbing_service._indexing_tasks.add(task)
        task.add_done_callback(dubbing_service._indexing_tasks.discard)
        assert not done                               # khong chan buoc tiep theo
        gate.set()
        await dubbing_service._wait_background_indexing(2)
    assert done == [21]
