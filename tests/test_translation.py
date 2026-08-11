from unittest.mock import AsyncMock, patch

import pytest

from app.models import Segment
from app.providers.base import ProviderInvalidResponse
from app.providers.gemini import LlmResult
from app.services import translation


def test_extract_json_handles_fenced_response():
    raw = '```json\n{"1": "xin chao", "2": "tam biet"}\n```'
    assert translation._extract_json(raw) == {"1": "xin chao", "2": "tam biet"}


def test_extract_json_handles_plain_response():
    raw = '{"1": "xin chao"}'
    assert translation._extract_json(raw) == {"1": "xin chao"}


def test_extract_json_raises_provider_invalid_response_on_garbage():
    with pytest.raises(ProviderInvalidResponse):
        translation._extract_json("khong phai json")


async def test_translate_batch_calls_gemini_twice_per_chunk_not_per_sentence():
    segments = [
        Segment(seq=1, start=0.0, end=3.0, text="Xin chao"),
        Segment(seq=2, start=3.0, end=6.0, text="Cam on ban"),
    ]
    generate_mock = AsyncMock(side_effect=[
        LlmResult(text='{"1": "Hello", "2": "Thank you"}', model="gemini-2.5-flash"),
        LlmResult(text='{"1": "Hi there", "2": "Thanks a lot"}', model="gemini-2.5-flash"),
    ])

    with patch("app.providers.gemini.generate", generate_mock):
        result = await translation.translate_batch(segments, "vi-VN", "en-US")

    assert result == ["Hi there", "Thanks a lot"]
    assert generate_mock.await_count == 2  # BAT BUOC: batch ca chunk, khong phai tung cau


async def test_translate_batch_empty_segments_does_not_call_gemini():
    generate_mock = AsyncMock()
    with patch("app.providers.gemini.generate", generate_mock):
        result = await translation.translate_batch([], "vi-VN", "en-US")
    assert result == []
    generate_mock.assert_not_awaited()
