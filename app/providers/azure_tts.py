"""Provider TTS — Azure Speech Service (thay cho edge-tts free trước đây).

REST API chính thức của Microsoft (có SLA, không phụ thuộc dịch vụ nội bộ trình
duyệt Edge) — 2 bước: đổi `Ocp-Apim-Subscription-Key` lấy access token (hết hạn
10 phút, cache lại và tự làm mới), rồi POST SSML tới endpoint tổng hợp giọng.

Giọng đọc (`voice_name`) BẮT BUỘC lấy từ bảng `voice_mappings` đang `is_active`
(BR-DUB-07) — tên giọng Azure Neural (vd. `vi-VN-HoaiMyNeural`) không đổi so với
edge-tts trước đây vì cả 2 đều dùng chung catalogue giọng Neural của Azure, nên
không cần cập nhật lại `voice_mappings` khi chuyển provider.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from xml.sax.saxutils import escape

import httpx

from app.audio_utils import measure_duration_sec
from app.config import settings
from app.providers.base import ProviderError, build_client, map_http_error

log = logging.getLogger(__name__)

_MAX_TTS_RETRIES = 3

# Token cấp bởi /sts/v1.0/issueToken hết hạn sau 10 phút — làm mới sớm hơn 1 phút
# để không bao giờ dùng token sắp hết hạn giữa chừng một lượt gọi.
_TOKEN_TTL_SEC = 9 * 60

_client: httpx.AsyncClient | None = None
_token: str | None = None
_token_fetched_at: float = 0.0
_token_lock = asyncio.Lock()


@dataclass(frozen=True)
class SynthesisResult:
    """Kết quả tổng hợp giọng cho MỘT câu thoại — khớp `edge_tts.SynthesisResult` cũ."""

    file_path: str
    duration_sec: float
    applied_rate: Decimal
    was_summarized: bool = False


def compute_rate_flag(r: Decimal) -> str:
    """Giữ nguyên logic cũ (BR-DUB-03 nhánh 2) — SSML `<prosody rate="...">` nhận
    cùng định dạng phần trăm ``"+15%"``/``"-5%"`` như tham số `--rate` của edge-tts.
    """
    percent = int(round((float(r) - 1.0) * 100))
    return f"+{percent}%" if percent >= 0 else f"{percent}%"


def _parse_rate_to_multiplier(rate: str | None) -> Decimal:
    if not rate:
        return Decimal("1.0")
    import re

    match = re.fullmatch(r"([+-]?\d+)%", rate.strip())
    if not match:
        return Decimal("1.0")
    return Decimal("1.0") + (Decimal(match.group(1)) / Decimal("100"))


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = build_client(
            f"https://{settings.azure_speech_region}.tts.speech.microsoft.com",
            read=30.0,
        )
    return _client


async def _issue_token() -> str:
    """Đổi subscription key lấy access token — endpoint RIÊNG, khác domain TTS."""
    url = f"https://{settings.azure_speech_region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                url, headers={"Ocp-Apim-Subscription-Key": settings.azure_speech_key}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise map_http_error(exc) from exc
    return response.text


async def _get_token() -> str:
    """Cache token, tự làm mới khi gần hết hạn — tránh gọi `/issueToken` mỗi câu thoại."""
    global _token, _token_fetched_at
    async with _token_lock:
        now = time.monotonic()
        if _token is None or (now - _token_fetched_at) > _TOKEN_TTL_SEC:
            _token = await _issue_token()
            _token_fetched_at = now
        return _token


def _build_ssml(text: str, voice_name: str, rate: str | None) -> str:
    # Suy ra `xml:lang` từ tiền tố tên giọng (vd. "vi-VN-HoaiMyNeural" -> "vi-VN") —
    # Azure yêu cầu khớp locale, không chấp nhận rỗng.
    lang = "-".join(voice_name.split("-")[:2])
    safe_text = escape(text)
    prosody_rate = rate or "+0%"
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
        f'<voice name="{voice_name}"><prosody rate="{prosody_rate}">{safe_text}</prosody></voice>'
        f"</speak>"
    )


async def synthesize(text: str, voice_name: str, output_path: str, rate: str | None = None) -> SynthesisResult:
    """Tổng hợp giọng đọc cho một câu thoại bằng Azure Speech REST API.

    `was_summarized` LUÔN trả `False` — giống quy ước cũ, tầng gọi
    (`dubbing_service`) tự gắn cờ này khi ghi `TranscriptSegment`.
    """
    ssml = _build_ssml(text, voice_name, rate)
    headers = {
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
    }

    last_error: Exception | None = None
    for attempt in range(1, _MAX_TTS_RETRIES + 1):
        try:
            token = await _get_token()
            response = await _get_client().post(
                "/cognitiveservices/v1",
                content=ssml.encode("utf-8"),
                headers={**headers, "Authorization": f"Bearer {token}"},
            )
            if response.status_code == 401:
                # Token có thể vừa bị thu hồi/hết hạn sớm hơn dự kiến — buộc lấy lại.
                global _token
                _token = None
                raise httpx.HTTPStatusError("401 Unauthorized", request=response.request, response=response)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if attempt == _MAX_TTS_RETRIES:
                break
            wait_sec = 1.5 * attempt
            log.warning(
                "Azure TTS loi (lan %s/%s), giong=%s: %s — retry sau %.1fs",
                attempt, _MAX_TTS_RETRIES, voice_name, exc, wait_sec,
            )
            await asyncio.sleep(wait_sec)

    if last_error is not None:
        if isinstance(last_error, httpx.HTTPError):
            raise map_http_error(last_error) from last_error
        raise last_error

    duration_sec = await measure_duration_sec(output_path)
    return SynthesisResult(
        file_path=output_path,
        duration_sec=duration_sec,
        applied_rate=_parse_rate_to_multiplier(rate),
        was_summarized=False,
    )


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
