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


# ---- Mở rộng 21/11/2026: Discovery, trợ lý giảng viên, kế hoạch học, giám sát thi ----

def test_extended_feature_defaults_are_low_and_tutor_chat_is_untouched():
    assert settings.discovery_thinking_level == "minimal"
    assert settings.instructor_ai_thinking_level == "minimal"
    assert settings.study_plan_thinking_level == "low"
    assert settings.proctoring_risk_thinking_level == "minimal"
    assert settings.proctoring_frame_thinking_level == "low"


@pytest.mark.asyncio
async def test_generate_with_tools_forwards_the_thinking_level():
    seen: dict = {}

    async def fake_conv(contents, **kw):
        seen.update(kw)
        return _ok()

    with patch.object(gemini, "generate_conversation", side_effect=fake_conv):
        await gemini.generate_with_tools("x", [{"functionDeclarations": []}], thinking_level="low")
        assert seen["thinking_level"] == "low"
        await gemini.generate_with_tools("x", [{"functionDeclarations": []}])
        assert seen["thinking_level"] is None


def test_tutor_chat_calls_do_not_set_a_thinking_level():
    """Gia sư AI hỏi đáp phải giữ mức suy nghĩ mặc định của model (cần suy luận); chỉ tiêu đề và giải thích quiz được hạ."""
    import inspect

    source = inspect.getsource(tutor_service)
    chat_start = source.index("async def _answer_with_context") if "async def _answer_with_context" in source else 0
    # Hai lệnh generate_conversation (hỏi đáp có/không có ngữ cảnh) không được truyền thinking_level.
    for chunk in source.split("gemini.generate_conversation(")[1:]:
        call = chunk.split(")\n", 1)[0]
        assert "thinking_level" not in call
