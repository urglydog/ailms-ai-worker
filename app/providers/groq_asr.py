"""Provider STT — Groq Cloud API (`whisper-large-v3-turbo`).

Đây là backend STT **mặc định** của dự án, theo §5.1.1 của KLTN: *"triệt tiêu phụ
thuộc GPU đắt đỏ tại Local"*. Server chỉ cần 4 vCPU / 8-16 GB RAM, không GPU.

⚠️ Điểm cần đo ở đầu Giai đoạn 5: BR-DUB-01 trong KLTN mô tả WhisperX với forced
alignment `wav2vec2`. Groq trả word-level timestamp từ API chứ không qua wav2vec2,
nên độ chính xác mốc thời gian có thể khác. Mốc thời gian ảnh hưởng trực tiếp tới
BR-DUB-03 (tính `T_orig`) và BR-TUTOR-02 (trích dẫn nhấp được), vì vậy phải đo đối
chứng với `whisperx_local` trên một video thật trước khi chốt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.providers.base import ProviderInvalidResponse, build_client, map_http_error

_BASE_URL = "https://api.groq.com/openai/v1"

# Client RIÊNG cho Groq (bulkhead). read=300s vì bóc băng một chunk 10 phút có thể lâu.
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = build_client(
            _BASE_URL,
            read=300.0,
            max_connections=10,
            max_keepalive=5,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        )
    return _client


async def aclose() -> None:
    """Gọi trong FastAPI lifespan khi shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@dataclass(frozen=True)
class WordTimestamp:
    """Một từ kèm mốc thời gian, đơn vị giây."""

    word: str
    start: float
    end: float


@dataclass(frozen=True)
class TranscriptionResult:
    """Kết quả bóc băng đã chuẩn hoá — độc lập với nhà cung cấp.

    Nhờ dataclass này mà đổi từ Groq sang WhisperX local không phải sửa tầng gọi.
    """

    text: str
    language: str
    duration_sec: float
    words: list[WordTimestamp] = field(default_factory=list)

    @property
    def speech_duration_sec(self) -> float:
        """Tổng thời lượng có lời thoại — dùng cho BR-DUB-10.

        Nếu tỉ lệ so với thời lượng video dưới 10%, job phải bị đánh dấu SKIPPED
        và KHÔNG đưa vào retry.
        """
        return sum(w.end - w.start for w in self.words)


async def transcribe(audio_path: str) -> TranscriptionResult:
    """Bóc băng một file audio, trả về mốc thời gian cấp độ từ (BR-DUB-01).

    Raises:
        ProviderError: đã chuẩn hoá, có cờ ``retryable`` cho tầng retry.
    """
    # TODO(Giai đoạn 5): hiện thực đầy đủ. Khung sườn Giai đoạn 0 chỉ định nghĩa
    # hợp đồng (kiểu vào/ra) để tầng gọi và test viết được trước.
    raise NotImplementedError(
        "transcribe() se duoc hien thuc o Giai doan 5. "
        "Xem skill lms-dubbing-pipeline de biet thu tu buoc."
    )


def _parse_response(payload: dict) -> TranscriptionResult:
    """Chuyển JSON của Groq thành dataclass. Sai định dạng thì raise, không trả dict."""
    try:
        words = [
            WordTimestamp(word=w["word"], start=float(w["start"]), end=float(w["end"]))
            for w in payload.get("words", [])
        ]
        return TranscriptionResult(
            text=payload["text"],
            language=payload.get("language", ""),
            duration_sec=float(payload.get("duration", 0.0)),
            words=words,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderInvalidResponse(f"Groq tra ve du lieu khong dung dinh dang: {exc}") from exc
