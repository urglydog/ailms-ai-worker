"""Provider LLM — Google Gemini API.

Dùng cho 4 việc khác nhau:
  · UC19 — dịch 3 bước (BR-DUB-02) và LLM Re-summarization khi R > 1.3 (BR-DUB-03)
  · UC25 — Creator Agent sinh Mindmap/Flashcards/Quiz (BR-MAT-04..06)
  · UC30 — Socratic Tutor (BR-TUTOR-01..04)
  · UC49 — Course Discovery qua Function Calling (BR-DISCOVERY-02)

BR-DUB-02: tên model đọc từ `settings.gemini_model` (biến môi trường),
TUYỆT ĐỐI không hardcode trong file này.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import settings
from app.providers.base import ProviderInvalidResponse, ProviderRateLimited, build_client, map_http_error

log = logging.getLogger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Tu gioi han RPM (doc/SETUP_GIAIDOAN5.md muc 3) — Gemini Free Tier ~15 RPM, tu dat
# thap hon (GEMINI_RATE_LIMIT_RPM mac dinh 12) de tru hao thay vi doi 429 roi moi retry.
_rate_lock = asyncio.Lock()
_call_timestamps: list[float] = []

# So lan tu retry rieng cho 1 loi tam thoi (429/timeout) cua Gemini — TACH KHOI retry
# cap chunk (BR-CHUNK-04, toi da 3 lan chay lai CA chunk). Retry o day re hon nhieu:
# chi goi lai 1 prompt, khong chay lai ASR/TTS.
_MAX_TRANSIENT_RETRIES = 3

# Client RIÊNG cho Gemini (bulkhead) — tách khỏi Groq và Edge-TTS.
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = build_client(
            _BASE_URL,
            read=120.0,
            max_connections=20,
            max_keepalive=10,
        )
    return _client


async def aclose() -> None:
    """Gọi trong FastAPI lifespan khi shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@dataclass(frozen=True)
class LlmResult:
    """Kết quả gọi LLM đã chuẩn hoá."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Ghi vào `ChatMessage.tokenUsed` để theo dõi chi phí (BR-TUTOR-04)."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class FunctionCall:
    """Lời gọi hàm do Gemini quyết định — dùng cho UC49.

    Course Discovery Agent dịch câu hỏi tự nhiên thành
    ``search_courses(category, level, price_type, keyword)``.
    """

    name: str
    arguments: dict


async def _throttle_rpm() -> None:
    """Chờ nếu đã gọi đủ `GEMINI_RATE_LIMIT_RPM` lần trong 60 giây gần nhất."""
    async with _rate_lock:
        now = time.monotonic()
        window_start = now - 60.0
        while _call_timestamps and _call_timestamps[0] < window_start:
            _call_timestamps.pop(0)
        if len(_call_timestamps) >= settings.gemini_rate_limit_rpm:
            wait_sec = 60.0 - (now - _call_timestamps[0])
            if wait_sec > 0:
                log.info("Gemini tu gioi han RPM: cho %.1fs truoc khi goi tiep", wait_sec)
                await asyncio.sleep(wait_sec)
        _call_timestamps.append(time.monotonic())


async def generate(prompt: str, *, system_instruction: str | None = None) -> LlmResult:
    """Sinh văn bản. Dùng cho dịch 3 bước (BR-DUB-02), LLM Re-summarization (BR-DUB-03).

    Tự giới hạn RPM (mục 3 `doc/SETUP_GIAIDOAN5.md`) VÀ tự retry riêng cho lỗi tạm
    thời — bao gồm CẢ HTTP 429, không chỉ timeout (yêu cầu bắt buộc, khác với suy
    diễn "chỉ retry timeout" từ văn bản BR-CHUNK-04 gốc).
    """
    body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    last_error: Exception | None = None
    for attempt in range(1, _MAX_TRANSIENT_RETRIES + 1):
        await _throttle_rpm()
        try:
            response = await get_client().post(
                f"/models/{settings.gemini_model}:generateContent",
                json=body,
                headers={"x-goog-api-key": settings.gemini_api_key},
            )
            response.raise_for_status()
            return _parse_response(response.json())
        except httpx.HTTPError as exc:
            error = map_http_error(exc)
            last_error = error
            if not error.retryable or attempt == _MAX_TRANSIENT_RETRIES:
                raise error from exc
            wait_sec = (
                error.retry_after_sec
                if isinstance(error, ProviderRateLimited) and error.retry_after_sec
                else 2**attempt
            )
            log.warning(
                "Gemini loi tam thoi (%s), retry sau %ss (lan %s/%s)",
                error.code, wait_sec, attempt, _MAX_TRANSIENT_RETRIES,
            )
            await asyncio.sleep(wait_sec)
    raise last_error  # pragma: no cover - vong for luon return hoac raise truoc do


async def generate_with_tools(prompt: str, tools: list[dict]) -> LlmResult | FunctionCall:
    """Gọi Gemini ở chế độ Function Calling — dùng cho UC49 Course Discovery."""
    # TODO(Giai đoạn 8): hiện thực cùng Course Discovery Agent.
    raise NotImplementedError(
        "generate_with_tools() se duoc hien thuc o Giai doan 8 (UC49 Course Discovery)."
    )


def _parse_response(payload: dict) -> LlmResult:
    """Chuyển JSON của Gemini thành dataclass; sai định dạng thì raise."""
    try:
        candidate = payload["candidates"][0]
        parts = candidate["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
        usage = payload.get("usageMetadata", {})
        return LlmResult(
            text=text,
            model=settings.gemini_model,
            prompt_tokens=int(usage.get("promptTokenCount", 0)),
            completion_tokens=int(usage.get("candidatesTokenCount", 0)),
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderInvalidResponse(f"Gemini tra ve du lieu khong dung dinh dang: {exc}") from exc
