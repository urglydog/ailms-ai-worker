"""Khóa API không được xuất hiện trong URL hay log (21/11/2026): khóa Gemini từng bị `httpx` in ra log vì nằm trong `?key=`."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import log_redaction
from app.providers import gemini

FAKE_KEY = "AQ.Zz9fakeFAKEfake1234567890abcdefghijk"


def _ok_json(text: str = "ok") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}}


def _response(json_body: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = json_body
    return r


@pytest.fixture(autouse=True)
def reset_key_pool():
    gemini._key_pool = None
    yield
    gemini._key_pool = None


def _use_key(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_rate_limit_rpm", 999)
    monkeypatch.setattr(gemini.settings, "gemini_api_keys", "")
    monkeypatch.setattr(gemini.settings, "gemini_api_key", FAKE_KEY)


async def test_generate_sends_the_key_in_a_header_not_in_the_url(monkeypatch):
    _use_key(monkeypatch)
    client = MagicMock()
    client.post = AsyncMock(return_value=_response(_ok_json()))

    with patch("app.providers.gemini.get_client", return_value=client):
        await gemini.generate("xin chao")

    args, kwargs = client.post.call_args
    assert "key=" not in args[0] and FAKE_KEY not in args[0]
    assert kwargs["headers"] == {"x-goog-api-key": FAKE_KEY}


async def test_embeddings_also_use_the_header(monkeypatch):
    _use_key(monkeypatch)
    monkeypatch.setattr(gemini.settings, "gemini_embedding_model", "gemini-embedding-001")
    client = MagicMock()
    client.post = AsyncMock(side_effect=[
        _response({"embedding": {"values": [0.1, 0.2]}}),
        _response({"embeddings": [{"values": [0.1]}, {"values": [0.2]}]}),
    ])

    with patch("app.providers.gemini.get_client", return_value=client):
        await gemini.embed_content("a")
        await gemini._batch_embed(["a", "b"])

    for call in client.post.call_args_list:
        assert "key=" not in call.args[0] and FAKE_KEY not in call.args[0]
        assert call.kwargs["headers"] == {"x-goog-api-key": FAKE_KEY}


def test_redact_masks_url_keys_and_google_key_shapes():
    assert log_redaction.redact(f"POST https://x/v1beta/models/m:generateContent?key={FAKE_KEY} 200") == "POST https://x/v1beta/models/m:generateContent?key=<redacted> 200"
    assert log_redaction.redact("a?b=1&api_key=abc123&c=2") == "a?b=1&api_key=<redacted>&c=2"
    assert FAKE_KEY not in log_redaction.redact(f"loi: {FAKE_KEY}")
    assert "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE" not in log_redaction.redact("k=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE")
    assert log_redaction.redact("khong co khoa o day") == "khong co khoa o day"


def test_httpx_logger_filter_cleans_the_record_even_if_a_key_slips_into_a_url(caplog):
    log_redaction.install()
    logger = logging.getLogger("httpx")
    with caplog.at_level(logging.INFO, logger="httpx"):
        logger.info('HTTP Request: %s %s "%s"', "POST", f"https://g.example/x?key={FAKE_KEY}", "HTTP/1.1 200 OK")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in text
    assert "<redacted>" in text


def test_install_is_idempotent():
    log_redaction.install()
    log_redaction.install()
    filters = [f for f in logging.getLogger("httpx").filters if isinstance(f, log_redaction.RedactSecretsFilter)]
    assert len(filters) == 1
