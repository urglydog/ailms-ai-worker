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
from dataclasses import dataclass
from decimal import Decimal

from app.config import settings

# Giới hạn phiên TTS đồng thời (bulkhead cho một provider không dùng HTTP pool).
_semaphore = asyncio.Semaphore(4)


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


async def synthesize(text: str, voice_name: str, output_path: str, rate: str | None = None) -> SynthesisResult:
    """Tổng hợp giọng đọc cho một câu thoại.

    Args:
        voice_name: lấy từ `voice_mappings.voice_name`, ví dụ ``vi-VN-HoaiMyNeural``.
                    KHÔNG hardcode (BR-DUB-07).
        rate: kết quả của :func:`compute_rate_flag`, hoặc None để giữ tốc độ chuẩn.
    """
    # TODO(Giai đoạn 5): hiện thực bằng edge_tts.Communicate.
    # Giai đoạn 0 chỉ chốt hợp đồng để tầng gọi và test viết được trước.
    async with _semaphore:
        raise NotImplementedError(
            "synthesize() se duoc hien thuc o Giai doan 5. "
            "Xem skill lms-dubbing-pipeline buoc 14."
        )


async def aclose() -> None:
    """Không có client HTTP nào phải đóng; giữ hàm này để lifespan gọi thống nhất."""
    return None
