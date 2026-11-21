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

from app import log_redaction
from app import usage as usage_mod
from app.config import settings
from app.providers.base import ProviderInvalidResponse, build_client

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Che khóa ở log của httpx/httpcore (xem app/log_redaction.py) — phòng thủ thêm ngoài việc khóa đi trong header.
log_redaction.install()


def _auth_headers(key: str) -> dict[str, str]:
    """Khóa API đi trong header, KHÔNG đặt trong URL: `httpx` ghi INFO nguyên URL của mỗi request nên khóa trong URL bị in ra log."""
    return {"x-goog-api-key": key}

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
                logger.info(f"Slot ****{slot['key'][-4:]}/{slot['model']} phuc hoi khoi cooldown.")
                return slot
            if self.cursor == start:
                break
        return None

    def mark_cool_down(self, key: str, model: str, duration_sec: int = 60, reason: str = "429") -> None:
        for slot in self.slots:
            if slot["key"] == key and slot["model"] == model:
                slot["status"] = "COOL_DOWN"
                slot["cool_down_until"] = time.time() + duration_sec
                active = self._active_count()
                logger.warning(f"Slot ****{key[-4:]}/{model} bi {reason} → cooldown {duration_sec}s. Con {active} slot active.")
                break

    def mark_failure(self, key: str, model: str) -> None:
        for slot in self.slots:
            if slot["key"] == key and slot["model"] == model:
                slot["failures"] += 1
                if slot["failures"] >= 3:
                    self.mark_cool_down(key, model, 30, reason="loi lien tiep (5xx)")
                break

    def mark_invalid(self, key: str, model: str) -> None:
        self.mark_cool_down(key, model, 3600, reason="key loi (400/403)")
        logger.error(f"Slot ****{key[-4:]}/{model} bi block (400/403) → cooldown 1h.")

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
                "key_preview": "****" + s["key"][-4:],
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
    """Gọi trong FastAPI lifespan khi shutdown, VÀ trong finally của mỗi task Celery
    (`_run_and_cleanup` ở `tasks/*.py`) — prefork worker tái sử dụng process cho nhiều
    task, mỗi task tự tạo event loop riêng qua `asyncio.run()`.

    BUG THẬT (25/09/2026, phát hiện lúc backfill embedding hàng loạt cho Course): `_rate_lock`
    là `asyncio.Lock()` module-level, tự bind vào event loop ĐẦU TIÊN dùng nó (Python 3.10+,
    xem `Lock._get_loop()`). Task Celery đầu tiên trong 1 worker process chạy xong, loop của
    nó đóng lại; task TIẾP THEO (loop mới) dùng lại đúng `_rate_lock` cũ vẫn còn trỏ về loop đã
    đóng → `RuntimeError: Event loop is closed` ngay ở `_throttle_rpm`. Phải tạo lock MỚI mỗi
    khi đóng client, giống hệt lý do `_client` phải reset về None.
    """
    global _client, _rate_lock
    if _client is not None:
        await _client.aclose()
        _client = None
    _rate_lock = asyncio.Lock()


@dataclass(frozen=True)
class LlmResult:
    """Kết quả gọi LLM đã chuẩn hoá."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Token "suy nghĩ" ẩn: không nằm trong completion_tokens nhưng Google vẫn tính tiền như token đầu ra.
    thinking_tokens: int = 0

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


def _parse_gemini_error_body(resp: httpx.Response) -> tuple[str, str]:
    """Đọc `error.status`/`error.message` từ response lỗi của Gemini, rỗng nếu parse thất bại."""
    try:
        error_body = resp.json().get("error", {})
        return str(error_body.get("status", "")), str(error_body.get("message", ""))
    except Exception:
        return "", ""


def _is_key_error(status_code: int, error_status: str, error_message: str) -> bool:
    """Phân biệt lỗi THẬT SỰ liên quan tới key (nên khoá) với lỗi payload của 1 request cụ thể
    (không liên quan tới sức khoẻ key, khoá oan sẽ giảm capacity cả pool). Dùng chung cho mọi
    endpoint Gemini (generateContent, embedContent...) — xem lịch sử bug 26/09/2026 ở
    `_execute_request`."""
    return (
        status_code == 403
        or error_status in ("PERMISSION_DENIED", "UNAUTHENTICATED")
        or "API_KEY_INVALID" in error_message
        or "API key not valid" in error_message
    )


def _is_credit_exhausted(resp: httpx.Response) -> bool:
    """HTTP 402 / thông báo "prepayment credits are depleted" — hết credit trả trước của dự án."""
    if resp.status_code == 402:
        return True
    _status, message = _parse_gemini_error_body(resp)
    return "credits are depleted" in message.lower() or "prepayment" in message.lower()


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
        url = f"{_BASE_URL}/models/{model}:generateContent"

        if attempt > 0:
            logger.info(f"Retry #{attempt}: dang thu slot ****{key[-4:]}/{model}")

        try:
            resp = await client.post(url, json=payload, headers=_auth_headers(key), timeout=60.0)

            if resp.status_code == 200:
                pool.reset_failure(key, model)
                body = resp.json()
                _report_text_usage(body, model)
                return _parse_response(body, model)

            if resp.status_code == 429:
                logger.warning(f"429 quota exceeded: ****{key[-4:]}/{model} → rotate sang slot tiep theo")
                pool.mark_cool_down(key, model, 60, reason="429")
                continue

            if resp.status_code in (400, 403):
                # BUG THẬT (26/09/2026, phát hiện lúc test proctoring với ảnh giả): trước đây
                # MỌI 400/403 đều bị coi là "key có vấn đề" và khoá 1h qua mark_invalid() — nhưng
                # 400 cũng là mã Google trả cho payload SAI của 1 request cụ thể (vd ảnh base64
                # hỏng), không liên quan gì tới sức khoẻ của key. 1 request test hỏng đã khoá oan
                # 1 key hoàn toàn khoẻ mạnh (quota còn dư theo dashboard) mất 1 tiếng. Đọc body lỗi
                # để phân biệt: chỉ khoá key khi Google thật sự báo lỗi liên quan tới auth/key.
                error_status, error_message = _parse_gemini_error_body(resp)
                if _is_key_error(resp.status_code, error_status, error_message):
                    pool.mark_invalid(key, model)
                    continue

                # 400 do payload của request này sai (vd ảnh không hợp lệ) — không phải lỗi key,
                # đổi sang slot khác cũng vô ích vì payload vẫn sai. Trả lỗi thẳng cho caller.
                logger.warning(
                    f"Gemini tu choi request (400 {error_status or 'khong ro'}): {error_message or resp.text[:200]}"
                )
                raise ProviderInvalidResponse(f"Gemini tu choi request: {error_message or resp.text[:200]}")

            if _is_credit_exhausted(resp):
                # 11/11/2026: hết credit trả trước (402) trước đây rơi vào nhánh 5xx, log chỉ báo
                # "network error"/"cooldown" gây hiểu nhầm. Khoá slot 1h, log rõ để Admin nạp tiền.
                logger.error(f"Gemini HET CREDIT (402) ****{key[-4:]}/{model}: {resp.text[:200]}")
                pool.mark_cool_down(key, model, 3600, reason="402-credit")
                continue

            # 5xx hoặc lỗi khác
            logger.warning(f"Gemini loi {resp.status_code} (****{key[-4:]}/{model}): {resp.text[:200]}")
            pool.mark_failure(key, model)
            continue

        except httpx.RequestError as exc:
            logger.error(f"Gemini network error (****{key[-4:]}/{model}): {exc}")
            pool.mark_failure(key, model)
            continue

    raise ProviderInvalidResponse("Max retries exceeded for Gemini API — tat ca slot deu that bai.")



async def generate_conversation(
    contents: list[dict], *, system_instruction: str | None = None, tools: list[dict] | None = None,
    response_mime_type: str | None = None, response_schema: dict | None = None,
    thinking_level: str | None = None,
) -> LlmResult | FunctionCall:
    """Lớp nền tảng cho mọi lệnh sinh văn bản — nhận thẳng `contents` đa lượt (multi-turn)
    thay vì 1 chuỗi prompt đơn, dùng cho UC30 Socratic Tutor cần nhớ lịch sử hội thoại
    (mỗi phần tử `{"role": "user"|"model", "parts": [{"text": ...}]}`). `generate()`/
    `generate_with_tools()` bên dưới chỉ là 2 lớp phủ tiện dụng cho trường hợp 1 lượt duy nhất,
    giữ nguyên chữ ký cũ để không phải sửa các nơi gọi khác (dịch, sinh học liệu, Discovery).
    """
    payload = {"contents": contents}
    if tools:
        payload["tools"] = tools
    if system_instruction:
        payload["systemInstruction"] = {
            "role": "system",
            "parts": [{"text": system_instruction}],
        }
    if response_mime_type:
        generation_config = payload.setdefault("generationConfig", {})
        generation_config["responseMimeType"] = response_mime_type
    if response_schema:
        generation_config = payload.setdefault("generationConfig", {})
        generation_config["responseSchema"] = response_schema
    if thinking_level:
        # Giới hạn token "suy nghĩ" ẩn (vẫn tính tiền) cho việc đơn giản như dịch/rút gọn câu.
        generation_config = payload.setdefault("generationConfig", {})
        generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    try:
        return await _execute_request(payload)
    except ProviderInvalidResponse as exc:
        # Model không hỗ trợ `thinkingLevel` (vd đổi sang model đời cũ): bỏ giới hạn suy nghĩ và gọi lại 1 lần thay vì làm hỏng cả tính năng.
        if thinking_level and "thinking" in str(exc).lower():
            logger.warning("Model khong nhan thinkingLevel=%s — goi lai khong gioi han suy nghi.", thinking_level)
            payload.get("generationConfig", {}).pop("thinkingConfig", None)
            return await _execute_request(payload)
        raise


async def generate(
    prompt: str, *, system_instruction: str | None = None, thinking_level: str | None = None,
) -> LlmResult:
    """Sinh văn bản 1 lượt. Dùng cho dịch 3 bước, re-summarization, sinh học liệu."""
    res = await generate_conversation(
        [{"role": "user", "parts": [{"text": prompt}]}], system_instruction=system_instruction,
        thinking_level=thinking_level,
    )
    if isinstance(res, FunctionCall):
        raise ProviderInvalidResponse("Expected text but got FunctionCall from Gemini")
    return res


async def generate_with_tools(prompt: str, tools: list[dict], *, system_instruction: str | None = None) -> LlmResult | FunctionCall:
    """Gọi Gemini ở chế độ Function Calling — dùng cho UC49 Course Discovery."""
    return await generate_conversation(
        [{"role": "user", "parts": [{"text": prompt}]}], system_instruction=system_instruction, tools=tools,
    )


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
        url = f"{_BASE_URL}/models/{settings.gemini_embedding_model}:embedContent"
        try:
            resp = await client.post(url, json=payload, headers=_auth_headers(key), timeout=30.0)
            if resp.status_code == 200:
                pool.reset_failure(key, slot["model"])
                values = resp.json().get("embedding", {}).get("values")
                if not values:
                    raise ProviderInvalidResponse("Gemini embedContent tra ve rong.")
                _report_embedding_usage(settings.gemini_embedding_model, [text])
                return values
            if resp.status_code == 429:
                pool.mark_cool_down(key, slot["model"], 60)
                continue
            if resp.status_code in (400, 403):
                # Cùng bug đã fix ở _execute_request (26/09/2026): 400 cũng là mã Google trả cho
                # payload SAI của request cụ thể (vd text rỗng/quá dài), không liên quan sức khoẻ
                # key — chỉ mark_invalid khi thật sự là lỗi key, tránh khoá oan 1h.
                error_status, error_message = _parse_gemini_error_body(resp)
                if _is_key_error(resp.status_code, error_status, error_message):
                    pool.mark_invalid(key, slot["model"])
                    continue
                logger.warning(
                    f"Gemini embedContent tu choi request (400 {error_status or 'khong ro'}): "
                    f"{error_message or resp.text[:200]}"
                )
                raise ProviderInvalidResponse(
                    f"Gemini embedContent tu choi request: {error_message or resp.text[:200]}"
                )
            if _is_credit_exhausted(resp):
                logger.error(f"Gemini embedContent HET CREDIT (402): {resp.text[:200]}")
                pool.mark_cool_down(key, slot["model"], 3600, reason="402-credit")
                continue
            pool.mark_failure(key, slot["model"])
        except httpx.RequestError as exc:
            logger.error(f"Gemini embedContent network error: {exc}")
            pool.mark_failure(key, slot["model"])

    raise ProviderInvalidResponse("Max retries exceeded for Gemini embedContent.")


_EMBED_BATCH_SIZE = 100   # giới hạn số request trong 1 lần batchEmbedContents


async def embed_contents(texts: list[str]) -> list[list[float]]:
    """Embedding NHIỀU đoạn văn bằng `batchEmbedContents` — 1 request cho tối đa 100 đoạn.

    Trước đây `tutor_indexing` gọi `embed_content` tuần tự từng câu: 90 câu = 90 request (~30 s
    mỗi bài, đo job 29). Cùng chính sách key pool/retry với `embed_content`.
    """
    out: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH_SIZE):
        out.extend(await _batch_embed(texts[start:start + _EMBED_BATCH_SIZE]))
    return out


async def _batch_embed(texts: list[str]) -> list[list[float]]:
    client = get_client()
    pool = get_key_pool()
    if not pool.slots:
        raise ProviderInvalidResponse("No Gemini API keys/models configured.")
    model_ref = f"models/{settings.gemini_embedding_model}"
    payload = {"requests": [
        {"model": model_ref, "content": {"parts": [{"text": t}]}, "outputDimensionality": settings.embedding_dimensions}
        for t in texts
    ]}

    for _attempt in range(_MAX_TRANSIENT_RETRIES):
        slot = pool.get_slot()
        if not slot:
            raise ProviderInvalidResponse("No active Gemini slot available (all in cooldown).")
        key = slot["key"]
        await _throttle_rpm()
        url = f"{_BASE_URL}/{model_ref}:batchEmbedContents"
        try:
            resp = await client.post(url, json=payload, headers=_auth_headers(key), timeout=60.0)
            if resp.status_code == 200:
                pool.reset_failure(key, slot["model"])
                vectors = [e.get("values") for e in resp.json().get("embeddings", [])]
                if len(vectors) != len(texts) or not all(vectors):
                    raise ProviderInvalidResponse("Gemini batchEmbedContents tra ve thieu vector.")
                _report_embedding_usage(settings.gemini_embedding_model, texts)
                return vectors
            if resp.status_code == 429:
                pool.mark_cool_down(key, slot["model"], 60)
                continue
            if resp.status_code in (400, 403):
                error_status, error_message = _parse_gemini_error_body(resp)
                if _is_key_error(resp.status_code, error_status, error_message):
                    pool.mark_invalid(key, slot["model"])
                    continue
                raise ProviderInvalidResponse(
                    f"Gemini batchEmbedContents tu choi request: {error_message or resp.text[:200]}"
                )
            if _is_credit_exhausted(resp):
                logger.error(f"Gemini batchEmbedContents HET CREDIT (402): {resp.text[:200]}")
                pool.mark_cool_down(key, slot["model"], 3600, reason="402-credit")
                continue
            pool.mark_failure(key, slot["model"])
        except httpx.RequestError as exc:
            logger.error(f"Gemini batchEmbedContents network error: {exc}")
            pool.mark_failure(key, slot["model"])

    raise ProviderInvalidResponse("Max retries exceeded for Gemini batchEmbedContents.")


def _report_embedding_usage(model: str, texts: list[str]) -> None:
    """Nhúng dữ liệu: API không trả số token nên ghi số ước lượng (đánh dấu estimated) để vẫn thấy được chi phí. Không bao giờ ném lỗi."""
    try:
        usage_mod.report_gemini(
            model=model,
            prompt_tokens=sum(usage_mod.estimate_tokens(t) for t in texts),
            completion_tokens=0,
            embedding=True,
            estimated=True,
        )
    except Exception:  # noqa: BLE001
        pass


def _report_text_usage(payload: dict, model: str) -> None:
    """Báo số token thật (gồm token suy nghĩ) của một lệnh sinh văn bản về BE để theo dõi chi phí. Không bao giờ ném lỗi."""
    try:
        usage = payload.get("usageMetadata", {}) or {}
        usage_mod.report_gemini(
            model=model,
            prompt_tokens=int(usage.get("promptTokenCount", 0)),
            completion_tokens=int(usage.get("candidatesTokenCount", 0)),
            thinking_tokens=int(usage.get("thoughtsTokenCount", 0)),
        )
    except Exception:  # noqa: BLE001
        pass


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
            thinking_tokens=int(usage.get("thoughtsTokenCount", 0)),
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderInvalidResponse(f"Gemini tra ve du lieu khong dung dinh dang: {exc}") from exc
