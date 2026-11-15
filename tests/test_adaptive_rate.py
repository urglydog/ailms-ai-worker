"""BR-DUB-03 — Adaptive Speech Rate, bản tối ưu tốc độ/chi phí (15/11/2026).

Chiều của R: code tính `R = T_exp/T_orig` (audio thực tế / khung gốc) — xem docstring
`dubbing_service._synthesize_segments`. R > 1.0 nghĩa là audio DÀI hơn khung, cần rút ngắn.

Khác bản cũ:
  · tăng tốc bằng FFmpeg `atempo` trên file có sẵn — KHÔNG gọi lại TTS chỉ để đổi `rate`;
  · rút gọn CẢ LÔ câu quá dài trong 1 lời gọi Gemini (`resummarize_batch`), không gọi từng câu;
  · các câu được tổng hợp song song.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.models import Segment
from app.providers.azure_tts import SynthesisResult
from app.services import dubbing_service

VOICE = "vi-VN-HoaiMyNeural"


def _res(duration_sec: float) -> SynthesisResult:
    return SynthesisResult(file_path="x.mp3", duration_sec=duration_sec, applied_rate=Decimal("1.0"), was_summarized=False)


def _tts_by_text(durations: dict[str, float]) -> AsyncMock:
    """TTS giả: độ dài audio phụ thuộc NỘI DUNG câu (để bản rút gọn ngắn hơn)."""
    return AsyncMock(side_effect=lambda text, voice, path, **kw: _res(durations[text]))


async def _run(segments, texts, tmp_path, tts_mock, batch_mock=None, tempo_mock=None):
    batch_mock = batch_mock or AsyncMock(side_effect=lambda items, lang: [t for t, _ in items])
    tempo_mock = tempo_mock or AsyncMock()
    paths = [tmp_path / f"s{i}.mp3" for i in range(len(segments))]
    with patch("app.providers.azure_tts.synthesize", tts_mock), \
         patch("app.services.translation.resummarize_batch", batch_mock), \
         patch("app.audio_utils.change_tempo", tempo_mock), \
         patch("app.services.dubbing_service._record_voice_chars_per_sec", AsyncMock()):
        out = await dubbing_service._synthesize_segments(segments, texts, VOICE, paths, "vi-VN")
    return out, batch_mock, tempo_mock


async def test_fits_frame_single_tts_call_no_tempo(tmp_path):
    seg = Segment(seq=1, start=0.0, end=5.0, text="x")
    tts = _tts_by_text({"ngan": 3.0})                              # R = 0.6
    out, batch, tempo = await _run([seg], ["ngan"], tmp_path, tts)

    assert tts.await_count == 1
    batch.assert_not_awaited()
    tempo.assert_not_awaited()
    assert out[0][0].applied_rate == Decimal("1.0") and out[0][2] is False


async def test_slightly_long_is_sped_up_locally_not_resynthesized(tmp_path):
    seg = Segment(seq=2, start=0.0, end=10.0, text="x")
    tts = _tts_by_text({"vua": 11.0})                              # R = 1.1
    out, batch, tempo = await _run([seg], ["vua"], tmp_path, tts)

    assert tts.await_count == 1                                    # KHONG goi lai TTS de doi rate
    batch.assert_not_awaited()
    assert abs(tempo.await_args.args[1] - 1.1) < 1e-9
    assert out[0][0].applied_rate == Decimal("1.1")
    assert abs(out[0][0].duration_sec - 10.0) < 1e-6


async def test_too_long_sentences_are_shortened_in_one_batch_call(tmp_path):
    segs = [Segment(seq=i, start=0.0, end=5.0, text="x") for i in range(3)]
    tts = _tts_by_text({"dai0": 8.0, "dai1": 8.0, "ok": 4.0, "gon0": 5.5, "gon1": 5.5})
    batch = AsyncMock(return_value=["gon0", "gon1"])
    out, batch, tempo = await _run(segs, ["dai0", "dai1", "ok"], tmp_path, tts, batch_mock=batch)

    assert batch.await_count == 1                                  # 1 loi goi cho ca lo
    items = batch.await_args.args[0]
    assert [t for t, _ in items] == ["dai0", "dai1"]
    assert all(max_chars >= 1 for _, max_chars in items)
    assert tts.await_count == 3 + 2                                # 3 lan dau + 2 cau rut gon
    assert [o[1] for o in out] == ["gon0", "gon1", "ok"]
    assert [o[2] for o in out] == [True, True, False]


async def test_resummarize_rounds_are_capped_then_max_tempo(tmp_path, monkeypatch):
    """Vòng rút gọn KHÔNG chạy vô hạn: tối đa `max_resummarize_attempts`, sau đó tăng tốc trần ×1.3."""
    monkeypatch.setattr(settings, "max_resummarize_attempts", 2)
    seg = Segment(seq=3, start=0.0, end=5.0, text="x")
    tts = AsyncMock(return_value=_res(8.0))                         # R = 1.6, khong bao gio cai thien
    batch = AsyncMock(side_effect=lambda items, lang: [t + "!" for t, _ in items])
    out, batch, tempo = await _run([seg], ["dai"], tmp_path, tts, batch_mock=batch)

    assert batch.await_count == 2
    assert tts.await_count == 1 + 2
    assert abs(tempo.await_args.args[1] - 1.3) < 1e-9
    assert out[0][0].applied_rate == Decimal("1.3") and out[0][2] is True


async def test_short_frame_skips_llm_and_uses_max_tempo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "min_resummarize_frame_sec", 2.0)
    seg = Segment(seq=5, start=0.0, end=1.2, text="Thank you.")
    tts = _tts_by_text({"Cam on cac ban.": 2.4})                   # R = 2.0
    out, batch, tempo = await _run([seg], ["Cam on cac ban."], tmp_path, tts)

    batch.assert_not_awaited()
    assert tts.await_count == 1
    assert abs(tempo.await_args.args[1] - 1.3) < 1e-9
    assert out[0][1] == "Cam on cac ban." and out[0][2] is False


async def test_batch_failure_falls_back_to_tempo(tmp_path):
    seg = Segment(seq=6, start=0.0, end=5.0, text="x")
    tts = AsyncMock(return_value=_res(8.0))
    batch = AsyncMock(side_effect=RuntimeError("gemini down"))
    out, _batch, tempo = await _run([seg], ["dai"], tmp_path, tts, batch_mock=batch)

    assert tts.await_count == 1
    assert out[0][0].applied_rate == Decimal("1.3")


async def test_tts_runs_concurrently_up_to_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tts_concurrency", 3)
    running = 0
    peak = 0

    async def slow_tts(text, voice, path, **kw):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return _res(1.0)

    segs = [Segment(seq=i, start=0.0, end=5.0, text="x") for i in range(10)]
    await _run(segs, ["a"] * 10, tmp_path, AsyncMock(side_effect=slow_tts))

    assert peak == 3


async def test_retry_reuses_cached_tts_files(tmp_path):
    """Chunk chạy lại: câu đã có file giọng cho đúng văn bản -> không gọi Azure lần nữa."""
    seg = Segment(seq=7, start=0.0, end=5.0, text="x")

    async def real_tts(text, voice, path, **kw):
        with open(path, "wb") as f:
            f.write(b"ID3fake")
        return _res(3.0)

    tts = AsyncMock(side_effect=real_tts)
    await _run([seg], ["ngan"], tmp_path, tts)
    await _run([seg], ["ngan"], tmp_path, tts)       # lan chay lai
    assert tts.await_count == 1

    await _run([seg], ["khac"], tmp_path, tts)       # van ban doi -> phai doc lai
    assert tts.await_count == 2


async def test_sped_up_file_is_not_reused_from_cache(tmp_path):
    seg = Segment(seq=8, start=0.0, end=10.0, text="x")

    async def real_tts(text, voice, path, **kw):
        with open(path, "wb") as f:
            f.write(b"ID3fake")
        return _res(11.0)                             # R = 1.1 -> bi tang toc tai cho

    tts = AsyncMock(side_effect=real_tts)
    await _run([seg], ["vua"], tmp_path, tts)
    await _run([seg], ["vua"], tmp_path, tts)
    assert tts.await_count == 2                      # file da doi toc do -> khong dung lai
