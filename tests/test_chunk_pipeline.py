"""Dây chuyền 2 công đoạn cho bài nhiều chunk (22/11/2026).

A (nhận dạng + dịch) của chunk k+1 chạy cùng lúc với B (TTS, ghép, upload, báo backend) của chunk k;
B vẫn chạy lần lượt -> backend nhận kết quả đúng thứ tự; số thứ tự câu nối tiếp; thử lại B không chạy
lại A.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.services import dubbing_service
from app.services.dubbing_service import SkippedPipelineError


def _ctx():
    return SimpleNamespace(
        video_source="UPLOAD", video_url="https://x/v.mp4", duration_sec=1500,   # 3 chunk 600/600/300
        source_transcript_available=False, lesson_id=21, target_language="vi-VN",
    )


async def _run(tmp_path, monkeypatch, prepare, finish):
    monkeypatch.setattr(settings, "temp_dir", str(tmp_path))
    monkeypatch.setattr(settings, "bgm_separation", "")
    monkeypatch.setattr(settings, "max_retry", 3)
    with patch("app.http.backend_client.get_context", AsyncMock(return_value=_ctx())), \
         patch("app.media.extract_audio_from_url", AsyncMock(side_effect=lambda url, p: open(p, "wb").write(b"w"))), \
         patch("app.http.backend_client.start_job", AsyncMock()), \
         patch("app.services.dubbing_service._prepare_chunk", prepare), \
         patch("app.services.dubbing_service._finish_chunk", finish), \
         patch("app.http.backend_client.finish_completed", AsyncMock()), \
         patch("app.http.backend_client.finish_skipped", AsyncMock()), \
         patch("app.redis_client.publish_progress", AsyncMock()), \
         patch("app.audio_utils.probe_audio", AsyncMock(return_value=(1500.0, 44100))), \
         patch("app.audio_utils.concat_files", AsyncMock(side_effect=lambda ps, out: open(out, "wb").write(b"x"))), \
         patch("app.services.dubbing_service.upload_file", AsyncMock(return_value="https://b2/final.mp3")), \
         patch("asyncio.sleep", AsyncMock()):
        return await dubbing_service.run_dubbing_pipeline(
            job_id=5, lesson_id=21, video_url="https://x/v.mp4", target_language="vi-VN",
        )


async def test_next_chunk_is_prepared_while_previous_chunk_finishes(tmp_path, monkeypatch):
    events = []
    a1_done = asyncio.Event()

    async def prepare(job_id, lesson_id, ctx, chunk, total, src, work, reuse, next_seq):
        events.append(("A start", chunk.index, next_seq))
        events.append(("A done", chunk.index))
        if chunk.index == 1:
            a1_done.set()
        return SimpleNamespace(consumed=10)

    async def finish(prepared, job_id, lesson_id, ctx, chunk, total, src, work, music_task):
        events.append(("B start", chunk.index))
        if chunk.index == 0:
            # B chunk 0 chi xong duoc khi A chunk 1 da chay -> neu khong chay chong thi test treo/that bai
            await asyncio.wait_for(a1_done.wait(), timeout=2)
        events.append(("B done", chunk.index))
        out = tmp_path / f"c{chunk.index}.mp3"
        out.write_bytes(b"a")
        return out, prepared.consumed

    result = await _run(tmp_path, monkeypatch, AsyncMock(side_effect=prepare), AsyncMock(side_effect=finish))
    assert result["status"] == "COMPLETED"

    # A cua chunk 1 xong TRUOC khi B cua chunk 0 xong -> co chay chong
    assert events.index(("A done", 1)) < events.index(("B done", 0))
    # B chay lan luot dung thu tu: chunk sau chi bat dau B khi chunk truoc xong B
    b = [e for e in events if e[0].startswith("B")]
    assert b == [("B start", 0), ("B done", 0), ("B start", 1), ("B done", 1), ("B start", 2), ("B done", 2)]
    # so thu tu cau noi tiep: 1, 11, 21
    assert [e[2] for e in events if e[0] == "A start"] == [1, 11, 21]


async def test_retrying_stage_b_reuses_stage_a_result(tmp_path, monkeypatch):
    prepare = AsyncMock(return_value=SimpleNamespace(consumed=5))
    attempts = {0: 0}

    async def finish(prepared, job_id, lesson_id, ctx, chunk, total, src, work, music_task):
        if chunk.index == 0:
            attempts[0] += 1
            if attempts[0] == 1:
                raise RuntimeError("azure tam loi")
        out = tmp_path / f"c{chunk.index}.mp3"
        out.write_bytes(b"a")
        return out, prepared.consumed

    result = await _run(tmp_path, monkeypatch, prepare, AsyncMock(side_effect=finish))
    assert result["status"] == "COMPLETED"
    assert attempts[0] == 2                         # B chunk 0 thu lai 1 lan
    assert prepare.await_count == 3                 # A moi chunk chi chay 1 lan (khong chay lai ASR)


async def test_skipped_in_later_chunk_still_skips_job(tmp_path, monkeypatch):
    async def prepare(job_id, lesson_id, ctx, chunk, total, src, work, reuse, next_seq):
        if chunk.index == 1:
            raise SkippedPipelineError("thoai < 10%")
        return SimpleNamespace(consumed=3)

    async def finish(prepared, *a, **k):
        out = tmp_path / "c.mp3"
        out.write_bytes(b"a")
        return out, 3

    result = await _run(tmp_path, monkeypatch, AsyncMock(side_effect=prepare), AsyncMock(side_effect=finish))
    assert result["status"] == "SKIPPED"
