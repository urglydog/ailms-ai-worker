"""Gia sư AI mở rộng (26/11/2026) — câu hỏi gợi ý theo bài + tóm tắt Insight cho giảng viên."""

from unittest.mock import AsyncMock, patch

import pytest

from app.providers.base import ProviderInvalidResponse
from app.providers.gemini import LlmResult
from app.services import tutor_suggestions


async def test_generate_questions_parses_fenced_json_and_dedupes():
    text = '```json\n["Vì sao dùng vòng lặp while?", "ngắn", "Vì sao dùng vòng lặp while?", "So sánh for và while?"]\n```'
    with patch("app.providers.gemini.generate", AsyncMock(return_value=LlmResult(text=text, model="m"))):
        result = await tutor_suggestions.generate_questions("Vòng lặp", "Chương 2", "", "transcript", 6)

    assert result == ["Vì sao dùng vòng lặp while?", "So sánh for và while?"]


async def test_generate_questions_raises_when_nothing_usable():
    with patch("app.providers.gemini.generate", AsyncMock(return_value=LlmResult(text="xin chao", model="m"))):
        with pytest.raises(ProviderInvalidResponse):
            await tutor_suggestions.generate_questions("Bai", "", "", "", 4)


async def test_generate_insight_summary_returns_summary_and_actions():
    text = 'Đây là kết quả: {"summary": "Học viên vướng ở bài 2.", "actions": ["Thêm ví dụ về con trỏ hàm"]}'
    with patch("app.providers.gemini.generate", AsyncMock(return_value=LlmResult(text=text, model="m"))) as gen:
        summary, actions = await tutor_suggestions.generate_insight_summary({"course_title": "C", "lessons": []})

    assert summary == "Học viên vướng ở bài 2."
    assert actions == ["Thêm ví dụ về con trỏ hàm"]
    assert "<stats>" in gen.call_args.args[0]


async def test_generate_insight_summary_rejects_empty_summary():
    with patch("app.providers.gemini.generate", AsyncMock(return_value=LlmResult(text='{"summary": ""}', model="m"))):
        with pytest.raises(ProviderInvalidResponse):
            await tutor_suggestions.generate_insight_summary({})
