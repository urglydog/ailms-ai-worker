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

from dataclasses import dataclass

import httpx

from app.config import settings
from app.providers.base import ProviderInvalidResponse, build_client

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

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


async def generate(prompt: str, *, system_instruction: str | None = None) -> LlmResult:
    """Sinh văn bản. Dùng cho dịch 3 bước, re-summarization, sinh học liệu."""
    # TODO(Giai đoạn 5): hiện thực. Giai đoạn 0 chỉ chốt hợp đồng.
    raise NotImplementedError(
        "generate() se duoc hien thuc o Giai doan 5 (dich 3 buoc BR-DUB-02)."
    )


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
