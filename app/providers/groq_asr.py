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
from pathlib import Path

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
class SttSegment:
    """Một câu/đoạn thoại (đơn vị Whisper `segments`) — dùng làm `TranscriptSegment`.

    Đây là đơn vị "câu" cho dịch thuật + TTS, thay cho spacy-based sentence
    splitting của VideoLingo (`core/_3_1_split_nlp.py`) — Groq đã trả sẵn ranh giới
    câu hợp lý qua `segments`, không cần thêm dependency NLP nặng.
    """

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    """Kết quả bóc băng đã chuẩn hoá — độc lập với nhà cung cấp.

    Nhờ dataclass này mà đổi từ Groq sang WhisperX local không phải sửa tầng gọi.
    """

    text: str
    language: str
    duration_sec: float
    words: list[WordTimestamp] = field(default_factory=list)
    segments: list[SttSegment] = field(default_factory=list)

    @property
    def speech_duration_sec(self) -> float:
        """Tổng thời lượng có lời thoại — dùng cho BR-DUB-10.

        Nếu tỉ lệ so với thời lượng video dưới 10%, job phải bị đánh dấu SKIPPED
        và KHÔNG đưa vào retry.
        """
        return sum(s.end - s.start for s in self.segments)


async def transcribe(audio_path: str) -> TranscriptionResult:
    """Bóc băng một file audio, trả về mốc thời gian cấp độ từ VÀ cấp độ câu (BR-DUB-01).

    Gọi Groq Whisper API (`whisper-large-v3-turbo` mặc định, đọc từ
    `settings.groq_asr_model` — không hardcode) ở `response_format=verbose_json`
    với cả 2 mức chi tiết `segment` (câu, dùng cho dịch + TTS) và `word` (dùng cho
    trích dẫn nhấp được của Socratic Tutor — BR-TUTOR-02).

    Raises:
        ProviderError: đã chuẩn hoá, có cờ ``retryable`` cho tầng retry (BR-CHUNK-04).
    """
    path = Path(audio_path)
    try:
        with path.open("rb") as f:
            response = await get_client().post(
                "/audio/transcriptions",
                data={
                    "model": settings.groq_asr_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": ["segment", "word"],
                },
                files={"file": (path.name, f, "application/octet-stream")},
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise map_http_error(exc) from exc
    return _parse_response(response.json())


def _parse_response(payload: dict) -> TranscriptionResult:
    """Chuyển JSON của Groq thành dataclass. Sai định dạng thì raise, không trả dict."""
    try:
        words = [
            WordTimestamp(word=w["word"], start=float(w["start"]), end=float(w["end"]))
            for w in payload.get("words", [])
        ]
        segments = [
            SttSegment(start=float(s["start"]), end=float(s["end"]), text=s["text"].strip())
            for s in payload.get("segments", [])
            if s.get("text", "").strip()
        ]
        return TranscriptionResult(
            text=payload["text"],
            language=payload.get("language", ""),
            duration_sec=float(payload.get("duration", 0.0)),
            words=words,
            segments=segments,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderInvalidResponse(f"Groq tra ve du lieu khong dung dinh dang: {exc}") from exc
