"""BR-DUB-03 — Adaptive Speech Rate, ĐẶC BIỆT là trần `MAX_RESUMMARIZE_ATTEMPTS`.

Văn bản BR-DUB-03 gốc không có điều kiện dừng cho vòng lặp Re-summarization —
`doc/SETUP_GIAIDOAN5.md` mục 4 yêu cầu bắt buộc phải thêm trần, nếu không có nguy cơ
lặp vô hạn khi câu đã quá ngắn mà R vẫn > 1.3. Test ở đây xác nhận vòng lặp DỪNG
đúng sau đúng số lần cho phép và KHÔNG BAO GIỜ chạy vô hạn.

Lưu ý về chiều của R: xem comment trong `dubbing_service._synthesize_with_adaptive_rate`
— code tính `R = T_exp/T_orig` (audio thực tế / khung thời gian gốc), NGƯỢC với công
thức "R = T_orig/T_exp" viết trong tài liệu, vì áp dụng đúng y văn bản sẽ khiến nhánh
"tăng tốc" kích hoạt khi audio đã NGẮN hơn khung gốc — vô nghĩa và mâu thuẫn với chính
thuật toán gốc VideoLingo (`core/_8_2_dub_chunks.py`). Các test dưới đây dùng chiều đã
sửa: R > 1.0 nghĩa là audio DÀI hơn khung gốc, cần rút ngắn.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.models import Segment
from app.providers.edge_tts import SynthesisResult
from app.services import dubbing_service


def _synth_result(duration_sec: float) -> SynthesisResult:
    return SynthesisResult(file_path="x.mp3", duration_sec=duration_sec, applied_rate=Decimal("1.0"), was_summarized=False)


async def test_r_at_or_below_1_keeps_normal_speed_and_pads_silence(tmp_path):
    segment = Segment(seq=1, start=0.0, end=5.0, text="cau ngan")  # T_orig = 5s
    # audio thuc te 3s <= T_orig(5s) -> R = 3/5 = 0.6 <= 1.0
    synthesize_mock = AsyncMock(return_value=_synth_result(3.0))
    resummarize_mock = AsyncMock()
    pad_silence_mock = AsyncMock()

    with patch("app.providers.edge_tts.synthesize", synthesize_mock), \
         patch("app.services.translation.resummarize", resummarize_mock), \
         patch("app.audio_utils.pad_silence", pad_silence_mock):
        result, final_text, was_summarized = await dubbing_service._synthesize_with_adaptive_rate(
            segment, "cau ngan", "vi-VN-HoaiMyNeural", tmp_path / "out.mp3", "vi-VN",
        )

    assert was_summarized is False
    resummarize_mock.assert_not_awaited()
    assert synthesize_mock.await_count == 1  # khong can tong hop lai, chi can chen lang
    pad_silence_mock.assert_awaited_once()
    pad_sec = pad_silence_mock.await_args.args[1]
    assert pad_sec == 2.0  # 5s (T_orig) - 3s (thuc te) = 2s can chen


async def test_r_between_1_and_1_3_applies_rate_flag_without_resummarize(tmp_path):
    segment = Segment(seq=2, start=0.0, end=10.0, text="cau vua")  # T_orig = 10s
    # audio thuc te 11s -> R = 11/10 = 1.1 (trong khoang 1.0 < R <= 1.3) -> can tang toc
    synthesize_mock = AsyncMock(return_value=_synth_result(11.0))
    resummarize_mock = AsyncMock()

    with patch("app.providers.edge_tts.synthesize", synthesize_mock), \
         patch("app.services.translation.resummarize", resummarize_mock):
        await dubbing_service._synthesize_with_adaptive_rate(
            segment, "cau vua", "vi-VN-HoaiMyNeural", tmp_path / "out.mp3", "vi-VN",
        )

    resummarize_mock.assert_not_awaited()
    assert synthesize_mock.await_count == 2  # 1 do luong ban dau + 1 lan ap dung rate
    second_call = synthesize_mock.await_args_list[-1]
    assert second_call.kwargs.get("rate") == "+10%"


async def test_r_above_1_3_stops_after_max_resummarize_attempts_and_applies_30_percent(tmp_path, monkeypatch):
    """Test QUAN TRỌNG NHẤT: xác nhận vòng lặp Re-summarization KHÔNG chạy vô hạn."""
    monkeypatch.setattr(settings, "max_resummarize_attempts", 2)

    segment = Segment(seq=3, start=0.0, end=5.0, text="cau qua dai can rut gon")  # T_orig = 5s
    # audio thuc te 8s -> R = 8/5 = 1.6 > 1.3, KHONG DOI du sau moi lan resummarize (mock co dinh)
    synthesize_mock = AsyncMock(return_value=_synth_result(8.0))
    resummarize_mock = AsyncMock(side_effect=lambda text, lang: text + " (rut gon)")

    with patch("app.providers.edge_tts.synthesize", synthesize_mock), \
         patch("app.services.translation.resummarize", resummarize_mock):
        result, final_text, was_summarized = await dubbing_service._synthesize_with_adaptive_rate(
            segment, "cau qua dai can rut gon", "vi-VN-HoaiMyNeural", tmp_path / "out.mp3", "vi-VN",
        )

    # Dung DUNG BANG so lan cho phep, khong hon (moi lan van R > 1.3 vi mock khong bao gio cai thien)
    assert resummarize_mock.await_count == settings.max_resummarize_attempts == 2
    assert was_summarized is True

    # 1 lan do ban dau + 2 lan trong vong lap + 1 lan ap dung rate toi da cuoi cung
    assert synthesize_mock.await_count == 1 + settings.max_resummarize_attempts + 1

    last_call = synthesize_mock.await_args_list[-1]
    assert last_call.kwargs.get("rate") == dubbing_service.MAX_TTS_RATE == "+30%"


async def test_r_recovers_within_attempts_stops_resummarize_loop_early(tmp_path):
    """Nếu R về dưới 1.3 sau 1 lần rút gọn thì KHÔNG được rút gọn thêm lần nữa."""
    segment = Segment(seq=4, start=0.0, end=5.0, text="cau dai")  # T_orig = 5s

    # Lan 1: audio 8s -> R=1.6>1.3. Sau 1 lan resummarize, audio con 5.5s -> R=1.1<=1.3 -> dung.
    durations = iter([8.0, 5.5])
    synthesize_mock = AsyncMock(side_effect=lambda *a, **k: _synth_result(next(durations, 5.5)))
    resummarize_mock = AsyncMock(side_effect=lambda text, lang: text + " (rut gon)")

    with patch("app.providers.edge_tts.synthesize", synthesize_mock), \
         patch("app.services.translation.resummarize", resummarize_mock):
        await dubbing_service._synthesize_with_adaptive_rate(
            segment, "cau dai", "vi-VN-HoaiMyNeural", tmp_path / "out.mp3", "vi-VN",
        )

    assert resummarize_mock.await_count == 1  # dung ngay khi R da <= 1.3, khong lam het so lan cho phep
