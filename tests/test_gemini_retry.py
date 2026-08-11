"""doc/SETUP_GIAIDOAN5.md mục 3 — retry của Gemini phải cover CẢ HTTP 429, không chỉ
timeout. Nhánh F8.2 (`KeyPoolManager`, merge vào F5.2) mở rộng thêm: khi bị 429/lỗi,
xoay sang KEY KHÁC trong pool thay vì chỉ chờ rồi gọi lại cùng key.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers import gemini
from app.providers.base import ProviderInvalidResponse


def _response(status_code: int, json_body: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    if json_body is not None:
        response.json.return_value = json_body
    return response


def _ok_json(text: str) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    }


@pytest.fixture(autouse=True)
def reset_key_pool():
    """`get_key_pool()` cache 1 singleton toàn module — phải reset giữa các test."""
    gemini._key_pool = None
    yield
    gemini._key_pool = None


async def test_generate_retries_with_second_key_after_429(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_rate_limit_rpm", 999)
    monkeypatch.setattr(gemini.settings, "gemini_api_keys", "key1,key2")
    monkeypatch.setattr(gemini.settings, "gemini_api_key", "")

    client = MagicMock()
    client.post = AsyncMock(side_effect=[_response(429), _response(200, _ok_json("xin chao"))])

    with patch("app.providers.gemini.get_client", return_value=client):
        result = await gemini.generate("dich cau nay")

    assert result.text == "xin chao"
    assert client.post.await_count == 2


async def test_generate_raises_when_single_key_hits_429(monkeypatch):
    """Chỉ 1 key: dính 429 là key đó vào cooldown ngay, không còn key nào active nữa
    trong lần gọi này — KHÔNG lặp vô hạn chờ cùng 1 key.
    """
    monkeypatch.setattr(gemini.settings, "gemini_api_keys", "")
    monkeypatch.setattr(gemini.settings, "gemini_api_key", "only-key")

    client = MagicMock()
    client.post = AsyncMock(return_value=_response(429))

    with patch("app.providers.gemini.get_client", return_value=client):
        with pytest.raises(ProviderInvalidResponse):
            await gemini.generate("dich cau nay")

    assert client.post.await_count == 1


async def test_generate_does_not_retry_on_malformed_response(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_api_keys", "")
    monkeypatch.setattr(gemini.settings, "gemini_api_key", "only-key")

    client = MagicMock()
    client.post = AsyncMock(return_value=_response(200, {"unexpected": "shape"}))

    with patch("app.providers.gemini.get_client", return_value=client):
        with pytest.raises(ProviderInvalidResponse):
            await gemini.generate("dich cau nay")

    assert client.post.await_count == 1  # lỗi định dạng KHÔNG được retry


async def test_generate_gives_up_after_trying_every_key_once(monkeypatch):
    """3 key, cả 3 đều lỗi 500 -> thử đúng số key rồi báo lỗi, KHÔNG lặp vô hạn."""
    monkeypatch.setattr(gemini.settings, "gemini_api_keys", "key1,key2,key3")
    monkeypatch.setattr(gemini.settings, "gemini_api_key", "")

    client = MagicMock()
    client.post = AsyncMock(return_value=_response(500))

    with patch("app.providers.gemini.get_client", return_value=client):
        with pytest.raises(ProviderInvalidResponse):
            await gemini.generate("dich cau nay")

    assert client.post.await_count == 3  # max(len(keys)=3, _MAX_TRANSIENT_RETRIES=3)
