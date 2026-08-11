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
from app.providers.base import ProviderInvalidResponse, build_client

log = logging.getLogger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Tự giới hạn RPM (doc/SETUP_GIAIDOAN5.md mục 3) — Gemini Free Tier ~15 RPM, tự đặt
# thấp hơn (GEMINI_RATE_LIMIT_RPM mặc định 12) để giảm khả năng dính 429 ngay từ đầu.
# BỔ SUNG cho KeyPoolManager bên dưới, KHÔNG thay thế: throttle giảm TẦN SUẤT gọi,
# key pool xử lý phần còn lại khi vẫn bị 429 dù đã throttle (ví dụ nhiều worker cùng chạy).
_rate_lock = asyncio.Lock()
_call_timestamps: list[float] = []
_MAX_TRANSIENT_RETRIES = 3

# Client RIÊNG cho Gemini (bulkhead) — tách khỏi Groq và Edge-TTS.
_client: httpx.AsyncClient | None = None


class KeyPoolManager:
    """Xoay vòng nhiều Gemini API key (UC49/F8.2) — key bị 429/400/403 vào cooldown
    thay vì làm cả pipeline dừng hẳn. `GEMINI_API_KEYS` (nhiều key, phân cách bằng dấu
    phẩy) là tùy chọn; không đặt thì rơi về đúng 1 key `GEMINI_API_KEY`.
    """

    def __init__(self, keys_str: str, single_key: str):
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not keys and single_key.strip():
            keys = [single_key.strip()]
        self.keys = [{"value": k, "status": "ACTIVE", "cool_down_until": 0, "failures": 0} for k in set(keys)]
        self.cursor = 0

    def get_key(self) -> str | None:
        if not self.keys:
            return None
        now = time.time()
        start_cursor = self.cursor
        while True:
            key_info = self.keys[self.cursor]
            self.cursor = (self.cursor + 1) % len(self.keys)

            if key_info["status"] == "ACTIVE":
                return key_info["value"]
            elif key_info["status"] == "COOL_DOWN":
                if now > key_info["cool_down_until"]:
                    key_info["status"] = "ACTIVE"
                    key_info["failures"] = 0
                    return key_info["value"]

            if self.cursor == start_cursor:
                break
        return None

    def mark_cool_down(self, key: str, duration_sec: int = 60):
        for k in self.keys:
            if k["value"] == key:
                k["status"] = "COOL_DOWN"
                k["cool_down_until"] = time.time() + duration_sec
                log.warning("Gemini API key rotated. Cooldown %ss.", duration_sec)
                break

    def mark_failure(self, key: str):
        for k in self.keys:
            if k["value"] == key:
                k["failures"] += 1
                if k["failures"] >= 3:
                    self.mark_cool_down(key, 30)
                break

    def reset_failure(self, key: str):
        for k in self.keys:
            if k["value"] == key:
                k["failures"] = 0
                break


_key_pool: KeyPoolManager | None = None


def get_key_pool() -> KeyPoolManager:
    global _key_pool
    if _key_pool is None:
        _key_pool = KeyPoolManager(settings.gemini_api_keys, settings.gemini_api_key)
    return _key_pool


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


async def _execute_request(payload: dict) -> LlmResult | FunctionCall:
    """Gọi Gemini — tự throttle RPM trước mỗi lần gọi VÀ tự xoay key khi bị 429/lỗi
    (BR-CHUNK-04 mở rộng: retry phải cover cả 429, không chỉ timeout — ở đây thêm một
    bậc nữa là đổi hẳn sang key khác thay vì chỉ chờ rồi gọi lại cùng key).
    """
    client = get_client()
    pool = get_key_pool()
    if not pool.keys:
        raise ProviderInvalidResponse("No Gemini API keys configured.")

    max_retries = max(len(pool.keys), _MAX_TRANSIENT_RETRIES)

    for _ in range(max_retries):
        key = pool.get_key()
        if not key:
            raise ProviderInvalidResponse("No active Gemini API keys available (all in cooldown).")

        await _throttle_rpm()
        url = f"{_BASE_URL}/models/{settings.gemini_model}:generateContent?key={key}"
        try:
            resp = await client.post(url, json=payload)

            if resp.status_code == 200:
                pool.reset_failure(key)
                return _parse_response(resp.json())

            if resp.status_code == 429:
                pool.mark_cool_down(key, 60)
                continue

            if resp.status_code in (400, 403):
                # Nhiều khả năng key sai/bị chặn — cooldown dài hơn nhiều so với 429.
                pool.mark_cool_down(key, 3600)
                continue

            # Lỗi khác (vd. 500) — tính vào số lần thất bại của KEY, không cooldown ngay.
            pool.mark_failure(key)
            continue

        except httpx.RequestError as exc:
            log.error("Gemini API request error: %s", exc)
            pool.mark_failure(key)
            continue

    raise ProviderInvalidResponse("Max retries exceeded for Gemini API.")


async def generate(prompt: str, *, system_instruction: str | None = None) -> LlmResult:
    """Sinh văn bản. Dùng cho dịch 3 bước (BR-DUB-02), LLM Re-summarization (BR-DUB-03)."""
    payload: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if system_instruction:
        payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_instruction}]}

    result = await _execute_request(payload)
    if isinstance(result, FunctionCall):
        raise ProviderInvalidResponse("Expected text but got FunctionCall from Gemini")
    return result


async def generate_with_tools(prompt: str, tools: list[dict], *, system_instruction: str | None = None) -> LlmResult | FunctionCall:
    """Gọi Gemini ở chế độ Function Calling — dùng cho UC49 Course Discovery."""
    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": tools,
    }
    if system_instruction:
        payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_instruction}]}
    return await _execute_request(payload)


def _parse_response(payload: dict) -> LlmResult | FunctionCall:
    """Chuyển JSON của Gemini thành dataclass; sai định dạng thì raise."""
    try:
        candidate = payload["candidates"][0]
        parts = candidate["content"]["parts"]

        for p in parts:
            if "functionCall" in p:
                return FunctionCall(
                    name=p["functionCall"]["name"],
                    arguments=p["functionCall"].get("args", {}),
                )

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
