"""doc/SETUP_GIAIDOAN5.md mục 3 — retry của Gemini phải cover CẢ HTTP 429, không chỉ
timeout (yêu cầu bắt buộc, khác suy diễn "chỉ retry timeout" từ BR-CHUNK-04 gốc).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers import gemini
from app.providers.base import ProviderInvalidResponse


def _http_status_error(status_code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test/x")
    response = httpx.Response(status_code, request=request, headers=headers or {})
    return httpx.HTTPStatusError("boom", request=request, response=response)


def _ok_response(text: str) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    }
    return response


async def test_generate_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_rate_limit_rpm", 999)  # khong de rate-limit noi bo can tro test

    client = MagicMock()
    client.post = AsyncMock(side_effect=[_http_status_error(429), _ok_response("xin chao")])

    with patch("app.providers.gemini.get_client", return_value=client), \
         patch("asyncio.sleep", AsyncMock()):
        result = await gemini.generate("dich cau nay")

    assert result.text == "xin chao"
    assert client.post.await_count == 2


async def test_generate_gives_up_after_max_transient_retries(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_rate_limit_rpm", 999)

    client = MagicMock()
    client.post = AsyncMock(side_effect=[_http_status_error(429)] * gemini._MAX_TRANSIENT_RETRIES)

    with patch("app.providers.gemini.get_client", return_value=client), \
         patch("asyncio.sleep", AsyncMock()):
        with pytest.raises(Exception):  # ProviderRateLimited
            await gemini.generate("dich cau nay")

    assert client.post.await_count == gemini._MAX_TRANSIENT_RETRIES


async def test_generate_does_not_retry_on_invalid_response_format(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_rate_limit_rpm", 999)

    client = MagicMock()
    client.post = AsyncMock(return_value=_bad_json_response())

    with patch("app.providers.gemini.get_client", return_value=client):
        with pytest.raises(ProviderInvalidResponse):
            await gemini.generate("dich cau nay")

    assert client.post.await_count == 1  # loi dinh dang KHONG retryable, khong duoc goi lai


def _bad_json_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"unexpected": "shape"}
    return response
