"""Provider TTS — Edge-TTS.

Đặc biệt so với Groq/Gemini: `edge-tts` là thư viện Python nói WebSocket trực tiếp
tới dịch vụ Microsoft, không phải HTTP REST, nên ở đây không có `httpx.AsyncClient`.
Bù lại phải tự giới hạn số phiên đồng thời bằng semaphore để giữ đúng tinh thần
bulkhead: TTS chạy quá nhiều phiên song song không được làm ảnh hưởng phần còn lại.

Giọng đọc BẮT BUỘC lấy từ bảng `voice_mappings` đang `is_active` (BR-DUB-07) —
tuyệt đối không hardcode danh sách ngôn ngữ ở đây.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import edge_tts as _edge_tts_lib

from app.audio_utils import measure_duration_sec

log = logging.getLogger(__name__)

# Giới hạn phiên TTS đồng thời (bulkhead cho một provider không dùng HTTP pool).
_semaphore = asyncio.Semaphore(4)

# Edge-TTS thỉnh thoảng trả "No audio was received" khi bị gọi dồn dập (nghẽn/rate-limit
# phía Microsoft) dù key/voice/text đều hợp lệ — quan sát thực tế: 1 chunk có thể gọi TTS
# 4-5 lần liên tiếp (câu gốc + tối đa 2 lần re-summarize BR-DUB-03 + rate cuối). Retry NGAY
# TẠI ĐÂY (rẻ, chỉ tốn 1 lệnh TTS) thay vì để lỗi bubble lên buộc `_process_chunk_with_retry`
# chạy lại TOÀN BỘ ASR + 2 lượt dịch Gemini của cả chunk chỉ vì TTS glitch thoáng qua.
_MAX_TTS_RETRIES = 3


@dataclass(frozen=True)
class SynthesisResult:
    """Kết quả tổng hợp giọng cho MỘT câu thoại."""

    file_path: str
    duration_sec: float
    #: Hệ số R đã áp dụng, ghi vào `TranscriptSegment.speechRate` (BR-DUB-03)
    applied_rate: Decimal
    #: True nếu câu này đã phải qua LLM Re-summarization vì R > 1.3
    was_summarized: bool = False


def compute_rate_flag(r: Decimal) -> str:
    """Chuyển hệ số R thành tham số `--rate` của Edge-TTS (BR-DUB-03 nhánh 2).

    Chỉ dùng cho khoảng ``1.0 < R <= 1.3``. Ví dụ ``R = 1.15`` -> ``"+15%"``.

    Ba nhánh của BR-DUB-03:
      * ``R <= 1.0``  — giữ tốc độ chuẩn, chèn silence padding cuối câu
      * ``1.0 < R <= 1.3`` — truyền rate flag này vào Edge-TTS
      * ``R > 1.3``  — KHÔNG ép tốc độ, bắt buộc gọi LLM Re-summarization rồi tính lại R
    """
    percent = int(round((float(r) - 1.0) * 100))
    return f"+{percent}%" if percent >= 0 else f"{percent}%"


def _parse_rate_to_multiplier(rate: str | None) -> Decimal:
    """`"+15%"` -> `Decimal("1.15")`, `"-5%"` -> `Decimal("0.95")`, `None` -> `Decimal("1.0")`."""
    if not rate:
        return Decimal("1.0")
    match = re.fullmatch(r"([+-]?\d+)%", rate.strip())
    if not match:
        return Decimal("1.0")
    return Decimal("1.0") + (Decimal(match.group(1)) / Decimal("100"))


async def synthesize(text: str, voice_name: str, output_path: str, rate: str | None = None) -> SynthesisResult:
    """Tổng hợp giọng đọc cho một câu thoại bằng `edge_tts.Communicate`.

    Args:
        voice_name: lấy từ `voice_mappings.voice_name`, ví dụ ``vi-VN-HoaiMyNeural``.
                    KHÔNG hardcode (BR-DUB-07).
        rate: kết quả của :func:`compute_rate_flag`, hoặc None để giữ tốc độ chuẩn.

    `was_summarized` LUÔN trả `False` — hàm này không biết văn bản đã qua LLM
    Re-summarization hay chưa, tầng gọi (`dubbing_service`) tự gắn cờ đó khi ghi
    `TranscriptSegment` vì đó là quyết định ở tầng điều phối, không phải TTS.
    """
    async with _semaphore:
        last_error: Exception | None = None
        for attempt in range(1, _MAX_TTS_RETRIES + 1):
            try:
                communicate = _edge_tts_lib.Communicate(text, voice=voice_name, rate=rate or "+0%")
                await communicate.save(output_path)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt == _MAX_TTS_RETRIES:
                    break
                wait_sec = 1.5 * attempt
                log.warning(
                    "Edge-TTS loi (lan %s/%s), giong=%s: %s — retry sau %.1fs",
                    attempt, _MAX_TTS_RETRIES, voice_name, exc, wait_sec,
                )
                await asyncio.sleep(wait_sec)
        if last_error is not None:
            raise last_error

    duration_sec = await measure_duration_sec(output_path)
    return SynthesisResult(
        file_path=output_path,
        duration_sec=duration_sec,
        applied_rate=_parse_rate_to_multiplier(rate),
        was_summarized=False,
    )


async def aclose() -> None:
    """Không có client HTTP nào phải đóng; giữ hàm này để lifespan gọi thống nhất."""
    return None
