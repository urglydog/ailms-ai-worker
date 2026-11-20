"""Mức "suy nghĩ" thấp cho các tính năng đơn giản (21/11/2026): đúng nơi, tắt được bằng cấu hình, và không làm hỏng tính năng khi model không hỗ trợ."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.providers import gemini
from app.providers.base import ProviderInvalidResponse
from app.providers.gemini import LlmResult
from app.services import tutor_service
from app.tasks import material


def _ok(text: str = "ok") -> LlmResult:
    return LlmResult(text=text, model="gemini-x", prompt_tokens=1, completion_tokens=1, thinking_tokens=0)


@pytest.mark.asyncio
async def test_unsupported_thinking_level_falls_back_to_no_limit_instead_of_failing():
    calls: list[dict] = []

    async def fake_execute(payload: dict):
        calls.append({k: (dict(v) if isinstance(v, dict) else v) for k, v in payload.items()})
        if len(calls) == 1:
            raise ProviderInvalidResponse("Gemini tu choi request: Thinking level is not supported for this model")
        return _ok()

    with patch.object(gemini, "_execute_request", side_effect=fake_execute):
        res = await gemini.generate("xin chao", thinking_level="low")

    assert res.text == "ok"
    assert len(calls) == 2
    assert calls[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "thinkingConfig" not in calls[1].get("generationConfig", {})


@pytest.mark.asyncio
async def test_other_400_errors_are_not_retried():
    with patch.object(gemini, "_execute_request", AsyncMock(side_effect=ProviderInvalidResponse("Gemini tu choi request: anh khong hop le"))) as ex:
        with pytest.raises(ProviderInvalidResponse):
            await gemini.generate("x", thinking_level="low")
    assert ex.await_count == 1


@pytest.mark.asyncio
async def test_no_retry_when_no_thinking_level_was_requested():
    with patch.object(gemini, "_execute_request", AsyncMock(side_effect=ProviderInvalidResponse("thinking something"))) as ex:
        with pytest.raises(ProviderInvalidResponse):
            await gemini.generate("x")
    assert ex.await_count == 1


def test_defaults_are_low_for_simple_features_and_core_features_are_untouched():
    assert settings.material_thinking_level == "low"
    assert settings.quiz_explain_thinking_level == "low"
    assert settings.aux_thinking_level == "minimal"


@pytest.mark.asyncio
async def test_tutor_title_and_quiz_explain_pass_their_levels():
    seen: list[str | None] = []

    async def fake_generate(prompt, **kwargs):
        seen.append(kwargs.get("thinking_level"))
        return _ok("Tieu de")

    with patch.object(tutor_service.gemini, "generate", side_effect=fake_generate):
        await tutor_service.generate_title("cau hoi", "tra loi")
        await tutor_service.answer_quiz_explanation("Giai thich dap an")

    assert seen == [settings.aux_thinking_level, settings.quiz_explain_thinking_level]


@pytest.mark.asyncio
async def test_empty_setting_turns_the_limit_off_again():
    seen: list[str | None] = []

    async def fake_generate(prompt, **kwargs):
        seen.append(kwargs.get("thinking_level"))
        return _ok("flowchart TD\nA-->B")

    with patch.object(material.gemini, "generate", side_effect=fake_generate), patch.object(settings, "material_thinking_level", ""):
        await material._generate_mindmap("noi dung", "vi-VN")

    assert seen and seen[0] is None


@pytest.mark.asyncio
async def test_mindmap_uses_the_material_level_by_default():
    seen: list[str | None] = []

    async def fake_generate(prompt, **kwargs):
        seen.append(kwargs.get("thinking_level"))
        return _ok("flowchart TD\nA-->B")

    with patch.object(material.gemini, "generate", side_effect=fake_generate):
        await material._generate_mindmap("noi dung", "vi-VN")

    assert seen == ["low"]
