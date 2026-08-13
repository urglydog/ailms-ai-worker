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
from dataclasses import dataclass
import time
import logging

import httpx

from app.config import settings
from app.providers.base import ProviderInvalidResponse, build_client

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

logger = logging.getLogger(__name__)

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
    """Quản lý danh sách (API Key x Model) theo round-robin.

    Mỗi "slot" là một cặp (key, model). Khi một slot bị 429 (quota hết),
    hệ thống tự động chuyển sang slot tiếp theo — đổi đồng thời cả key lẫn model
    nếu cần, không cần can thiệp thủ công.

    Thứ tự thử: key1+model1 → key2+model1 → ... → key1+model2 → key2+model2 → ...
    """

    def __init__(self, keys_str: str, single_key: str, models_str: str = "", primary_model: str = "gemini-2.0-flash"):
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not keys and single_key.strip():
            keys = [single_key.strip()]

        models = [m.strip() for m in models_str.split(",") if m.strip()]
        if not models:
            models = [primary_model.strip()] if primary_model.strip() else ["gemini-2.0-flash"]

        # Tạo tổ hợp key x model (key trước, model sau)
        self.slots: list[dict] = []
        for key in dict.fromkeys(keys):   # dict.fromkeys = giữ thứ tự, loại trùng
            for model in dict.fromkeys(models):
                self.slots.append({
                    "key": key,
                    "model": model,
                    "status": "ACTIVE",
                    "cool_down_until": 0.0,
                    "failures": 0,
                })
        self.cursor = 0
        logger.info(f"KeyPoolManager: {len(self.slots)} slot(s) — {len(keys)} key(s) x {len(models)} model(s)")

    def get_slot(self) -> dict | None:
        """Trả về slot (key + model) đang sẵn sàng, hoặc None nếu tất cả cooldown."""
        if not self.slots:
            return None
        now = time.time()
        start = self.cursor
        while True:
            slot = self.slots[self.cursor]
            self.cursor = (self.cursor + 1) % len(self.slots)
            if slot["status"] == "ACTIVE":
                return slot
            if slot["status"] == "COOL_DOWN" and now > slot["cool_down_until"]:
                slot["status"] = "ACTIVE"
                slot["failures"] = 0
                logger.info(f"Slot {slot['key'][:8]}.../{slot['model']} phuc hoi khoi cooldown.")
                return slot
            if self.cursor == start:
                break
        return None

    def mark_cool_down(self, key: str, model: str, duration_sec: int = 60) -> None:
        for slot in self.slots:
            if slot["key"] == key and slot["model"] == model:
                slot["status"] = "COOL_DOWN"
                slot["cool_down_until"] = time.time() + duration_sec
                active = self._active_count()
                logger.warning(f"Slot {key[:8]}.../{model} bi 429 → cooldown {duration_sec}s. Con {active} slot active.")
                break

    def mark_failure(self, key: str, model: str) -> None:
        for slot in self.slots:
            if slot["key"] == key and slot["model"] == model:
                slot["failures"] += 1
                if slot["failures"] >= 3:
                    self.mark_cool_down(key, model, 30)
                break

    def mark_invalid(self, key: str, model: str) -> None:
        self.mark_cool_down(key, model, 3600)
        logger.error(f"Slot {key[:8]}.../{model} bi block (400/403) → cooldown 1h.")

    def reset_failure(self, key: str, model: str) -> None:
        for slot in self.slots:
            if slot["key"] == key and slot["model"] == model:
                slot["failures"] = 0
                break

    def get_status(self) -> list[dict]:
        """Snapshot trạng thái để Admin Dashboard hiển thị."""
        now = time.time()
        return [
            {
                "key_preview": s["key"][:8] + "...",
                "model": s["model"],
                "status": s["status"],
                "in_cooldown": s["status"] == "COOL_DOWN" and s["cool_down_until"] > now,
                "cooldown_remaining_sec": max(0, int(s["cool_down_until"] - now)) if s["status"] == "COOL_DOWN" else 0,
                "failures": s["failures"],
            }
            for s in self.slots
        ]

    def _active_count(self) -> int:
        now = time.time()
        return sum(1 for s in self.slots if s["status"] == "ACTIVE" or (s["status"] == "COOL_DOWN" and s["cool_down_until"] <= now))

    # Backward-compat: giữ .keys cho code cũ
    @property
    def keys(self) -> list[dict]:
        return self.slots


_key_pool: KeyPoolManager | None = None

def get_key_pool() -> KeyPoolManager:
    global _key_pool
    if _key_pool is None:
        _key_pool = KeyPoolManager(
            settings.gemini_api_keys,
            settings.gemini_api_key,
            settings.gemini_models,
            settings.gemini_model,
        )
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
                logger.info(f"Gemini tu gioi han RPM: cho {wait_sec:.1f}s truoc khi goi tiep")
                await asyncio.sleep(wait_sec)
        _call_timestamps.append(time.monotonic())


async def _execute_request(payload: dict) -> LlmResult | FunctionCall:
    client = get_client()
    pool = get_key_pool()
    if not pool.slots:
        raise ProviderInvalidResponse("No Gemini API keys/models configured.")

    max_retries = max(len(pool.slots), _MAX_TRANSIENT_RETRIES)

    for attempt in range(max_retries):
        slot = pool.get_slot()
        if not slot:
            raise ProviderInvalidResponse("No active Gemini slot available (all in cooldown).")

        key = slot["key"]
        model = slot["model"]
        await _throttle_rpm()
        url = f"{_BASE_URL}/models/{model}:generateContent?key={key}"

        if attempt > 0:
            logger.info(f"Retry #{attempt}: dang thu slot {key[:8]}.../{model}")

        try:
            resp = await client.post(url, json=payload, timeout=60.0)

            if resp.status_code == 200:
                pool.reset_failure(key, model)
                return _parse_response(resp.json(), model)

            if resp.status_code == 429:
                logger.warning(f"429 quota exceeded: {key[:8]}.../{model} → rotate sang slot tiep theo")
                pool.mark_cool_down(key, model, 60)
                continue

            if resp.status_code in (400, 403):
                pool.mark_invalid(key, model)
                continue

            # 5xx hoặc lỗi khác
            pool.mark_failure(key, model)
            continue

        except httpx.RequestError as exc:
            logger.error(f"Gemini network error ({key[:8]}.../{model}): {exc}")
            pool.mark_failure(key, model)
            continue

    raise ProviderInvalidResponse("Max retries exceeded for Gemini API — tat ca slot deu that bai.")



async def generate(prompt: str, *, system_instruction: str | None = None) -> LlmResult:
    """Sinh văn bản. Dùng cho dịch 3 bước, re-summarization, sinh học liệu."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    }
    if system_instruction:
        payload["systemInstruction"] = {
            "role": "system",
            "parts": [{"text": system_instruction}],
        }
    res = await _execute_request(payload)
    if isinstance(res, FunctionCall):
        raise ProviderInvalidResponse("Expected text but got FunctionCall from Gemini")
    return res


async def generate_with_tools(prompt: str, tools: list[dict], *, system_instruction: str | None = None) -> LlmResult | FunctionCall:
    """Gọi Gemini ở chế độ Function Calling — dùng cho UC49 Course Discovery."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": tools,
    }
    if system_instruction:
        payload["systemInstruction"] = {
            "role": "system",
            "parts": [{"text": system_instruction}],
        }
    return await _execute_request(payload)


async def embed_content(text: str) -> list[float]:
    """Sinh vector embedding cho RAG của Socratic Tutor (BR-TUTOR-03/04).

    Dùng chung KeyPoolManager/throttle của `generate()` nhưng gọi endpoint
    `embedContent` riêng (khác `generateContent`) và KHÔNG đi qua `_execute_request`
    vì payload/response shape khác hẳn (không có `candidates`, không FunctionCall).
    `outputDimensionality` cắt gọn vector theo `settings.embedding_dimensions` — đã xác
    nhận Gemini hỗ trợ tham số này cho `settings.gemini_embedding_model`.
    """
    client = get_client()
    pool = get_key_pool()
    if not pool.slots:
        raise ProviderInvalidResponse("No Gemini API keys/models configured.")

    payload = {
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": settings.embedding_dimensions,
    }

    for attempt in range(_MAX_TRANSIENT_RETRIES):
        slot = pool.get_slot()
        if not slot:
            raise ProviderInvalidResponse("No active Gemini slot available (all in cooldown).")
        key = slot["key"]
        await _throttle_rpm()
        url = f"{_BASE_URL}/models/{settings.gemini_embedding_model}:embedContent?key={key}"
        try:
            resp = await client.post(url, json=payload, timeout=30.0)
            if resp.status_code == 200:
                pool.reset_failure(key, slot["model"])
                values = resp.json().get("embedding", {}).get("values")
                if not values:
                    raise ProviderInvalidResponse("Gemini embedContent tra ve rong.")
                return values
            if resp.status_code == 429:
                pool.mark_cool_down(key, slot["model"], 60)
                continue
            if resp.status_code in (400, 403):
                pool.mark_invalid(key, slot["model"])
                continue
            pool.mark_failure(key, slot["model"])
        except httpx.RequestError as exc:
            logger.error(f"Gemini embedContent network error: {exc}")
            pool.mark_failure(key, slot["model"])

    raise ProviderInvalidResponse("Max retries exceeded for Gemini embedContent.")


def _parse_response(payload: dict, model: str) -> LlmResult | FunctionCall:
    """Chuyển JSON của Gemini thành dataclass; sai định dạng thì raise."""
    try:
        candidate = payload["candidates"][0]
        parts = candidate["content"]["parts"]
        
        for p in parts:
            if "functionCall" in p:
                return FunctionCall(
                    name=p["functionCall"]["name"],
                    arguments=p["functionCall"].get("args", {})
                )
                
        text = "".join(p.get("text", "") for p in parts)
        usage = payload.get("usageMetadata", {})
        return LlmResult(
            text=text,
            model=model,
            prompt_tokens=int(usage.get("promptTokenCount", 0)),
            completion_tokens=int(usage.get("candidatesTokenCount", 0)),
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderInvalidResponse(f"Gemini tra ve du lieu khong dung dinh dang: {exc}") from exc
