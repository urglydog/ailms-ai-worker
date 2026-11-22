"""Điểm 2 (22/11/2026): bước ghép file cuối không làm việc thừa."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app import audio_utils, storage
from app.config import settings
from app.services import dubbing_service

from .test_timeline import _tone, needs_ffmpeg


def _ctx():
    return SimpleNamespace(
        video_source="UPLOAD", video_url="https://example.test/v.mp4", duration_sec=None,
        source_transcript_available=False, lesson_id=21, target_language="vi-VN",
    )


async def _run(tmp_path, monkeypatch, duration_sec, chunk_side_effect):
    monkeypatch.setattr(settings, "temp_dir", str(tmp_path))
    finish = AsyncMock()
    upload = AsyncMock(return_value="https://b2/final.mp3")
    with patch("app.http.backend_client.get_context", AsyncMock(return_value=_ctx())), \
         patch("app.media.extract_audio_from_url", AsyncMock()), \
         patch("app.media.probe_duration_sec", AsyncMock(return_value=duration_sec)), \
         patch("app.http.backend_client.start_job", AsyncMock()), \
         patch("app.services.dubbing_service._prepare_chunk_with_retry", AsyncMock(return_value=SimpleNamespace(consumed=0))), \
         patch("app.services.dubbing_service._finish_chunk_with_retry", AsyncMock(side_effect=chunk_side_effect)), \
         patch("app.http.backend_client.finish_completed", finish), \
         patch("app.redis_client.publish_progress", AsyncMock()), \
         patch("app.services.dubbing_service.upload_file", upload), \
         patch("app.audio_utils.probe_audio", AsyncMock(return_value=(300.4, 44100))), \
         patch("app.audio_utils.concat_files", AsyncMock(side_effect=lambda paths, out: open(out, "wb").write(b"x"))) as concat:
        result = await dubbing_service.run_dubbing_pipeline(
            job_id=7, lesson_id=21, video_url="https://example.test/v.mp4", target_language="vi-VN",
        )
    return result, finish, upload, concat


async def test_single_chunk_reuses_chunk_file_without_reencode_or_second_upload(tmp_path, monkeypatch):
    chunk_file = tmp_path / "chunk_0_dub.mp3"
    chunk_file.write_bytes(b"audio")
    result, finish, upload, concat = await _run(tmp_path, monkeypatch, 300, [(chunk_file, 10)])

    assert result["status"] == "COMPLETED"
    concat.assert_not_awaited()
    upload.assert_not_awaited()
    kwargs = finish.await_args.kwargs
    assert kwargs["final_url"] == storage.public_url("dubbing/21/vi-VN/chunk_0.mp3")
    assert kwargs["duration_sec"] == 300


async def test_multi_chunk_concats_and_uploads_final(tmp_path, monkeypatch):
    files = [tmp_path / f"c{i}.mp3" for i in range(2)]
    for f in files:
        f.write_bytes(b"a")
    result, finish, upload, concat = await _run(tmp_path, monkeypatch, 1200, [(files[0], 5), (files[1], 5)])

    assert result["status"] == "COMPLETED"
    concat.assert_awaited_once()
    upload.assert_awaited_once()
    assert finish.await_args.kwargs["final_url"] == "https://b2/final.mp3"


@needs_ffmpeg
@pytest.mark.asyncio
async def test_concat_same_format_is_copy_and_keeps_length(tmp_path):
    parts = [_tone(tmp_path, "a", 2.0), _tone(tmp_path, "b", 3.0)]
    out = tmp_path / "final.mp3"
    await audio_utils.concat_files(parts, out)
    # chep thang (-c copy): moi cho noi co the them ~1 khung MP3 (~26–50 ms), khong hon
    assert abs(await audio_utils.measure_duration_sec(out) - 5.0) < 0.12


@needs_ffmpeg
@pytest.mark.asyncio
async def test_concat_different_formats_reencodes(tmp_path):
    from pydub.generators import Sine

    a = tmp_path / "a.mp3"
    Sine(440).to_audio_segment(duration=2000).set_frame_rate(16000).export(str(a), format="mp3")
    b = _tone(tmp_path, "b", 3.0)            # 44,1 kHz
    out = tmp_path / "final.mp3"
    await audio_utils.concat_files([a, b], out)
    assert abs(await audio_utils.measure_duration_sec(out) - 5.0) < 0.12
