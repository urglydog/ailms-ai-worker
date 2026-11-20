"""Ghi nhận mức dùng AI (21/11/2026): mọi lệnh gọi Gemini/Groq báo token/giây thật về BE; nhãn tính năng; không bao giờ làm hỏng lệnh gọi AI."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import usage
from app.providers import gemini


@pytest.fixture
def sent():
    """Thu các body được gửi về BE (thay cho HTTP thật)."""
    bodies: list[dict] = []

    async def fake_report(body: dict) -> None:
        bodies.append(body)

    with patch("app.http.backend_client.report_ai_usage", side_effect=fake_report):
        yield bodies


async def _drain() -> None:
    # Cho các task gửi chạy xong.
    # Chỉ chờ task của event loop hiện tại: task còn sót từ test trước (loop đã đóng) không được gom vào.
    loop = asyncio.get_running_loop()
    for stale in [t for t in usage._pending if t.get_loop() is not loop]:
        usage._pending.discard(stale)
    while True:
        running = [t for t in usage._pending if not t.done()]
        if not running:
            break
        await asyncio.gather(*running)
    await asyncio.sleep(0)


def _ok_payload() -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": "xin chao"}]}}],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20, "thoughtsTokenCount": 300},
    }


async def test_text_usage_includes_thinking_tokens_and_the_feature_tag(sent):
    with usage.usage_tag("DUBBING_TRANSLATE", course_id=3, lesson_id=7):
        gemini._report_text_usage(_ok_payload(), "gemini-x")
        await _drain()

    assert len(sent) == 1
    body = sent[0]
    assert body["provider"] == "GEMINI"
    assert body["feature"] == "DUBBING_TRANSLATE"
    assert (body["promptTokens"], body["completionTokens"], body["thinkingTokens"]) == (100, 20, 300)
    assert body["courseId"] == 3 and body["lessonId"] == 7
    assert "cost" not in " ".join(body.keys()).lower()  # chi phí do BE tự tính, không gửi tiền


async def test_untagged_calls_are_still_recorded_so_gaps_are_visible(sent):
    gemini._report_text_usage(_ok_payload(), "gemini-x")
    await _drain()

    assert sent[0]["feature"] == "UNTAGGED"


async def test_features_already_logged_elsewhere_are_not_double_counted(sent):
    with usage.usage_tag("MATERIAL", already_logged=True):
        gemini._report_text_usage(_ok_payload(), "gemini-x")
        usage.report_groq_audio(model="whisper", audio_seconds=10)
        await _drain()

    assert sent == []


async def test_tag_does_not_leak_outside_its_block(sent):
    with usage.usage_tag("TUTOR_CHAT"):
        pass
    assert usage.current_tag() is None


async def test_nested_tag_overrides_the_outer_one(sent):
    with usage.usage_tag("DUBBING_TRANSCRIBE"):
        with usage.usage_tag("DUBBING_TRANSLATE"):
            gemini._report_text_usage(_ok_payload(), "m")
        usage.report_groq_audio(model="w", audio_seconds=61.4)
        await _drain()

    assert [b["feature"] for b in sent] == ["DUBBING_TRANSLATE", "DUBBING_TRANSCRIBE"]
    assert sent[1]["provider"] == "GROQ" and sent[1]["audioSeconds"] == 61


async def test_embedding_usage_is_estimated_and_flagged(sent):
    with usage.usage_tag("EMBEDDING_TUTOR"):
        gemini._report_embedding_usage("emb-model", ["a" * 400, "b" * 40])
        await _drain()

    body = sent[0]
    assert body["embedding"] is True and body["estimated"] is True
    assert body["promptTokens"] == 100 + 10 and body["completionTokens"] == 0


async def test_a_failing_backend_never_breaks_the_ai_call():
    with patch("app.http.backend_client.report_ai_usage", new=AsyncMock(side_effect=RuntimeError("be down"))):
        with usage.usage_tag("TUTOR_CHAT"):
            gemini._report_text_usage(_ok_payload(), "m")  # không ném
            await _drain()


def test_reporting_without_an_event_loop_is_silently_ignored():
    usage.report_gemini(model="m", prompt_tokens=1, completion_tokens=1)  # không ném


@pytest.mark.parametrize("payload", [{}, {"usageMetadata": None}, {"usageMetadata": {"promptTokenCount": "x"}}])
async def test_malformed_usage_metadata_is_ignored(payload, sent):
    gemini._report_text_usage(payload, "m")
    await _drain()

    assert len(sent) <= 1


async def test_tagged_decorator_sets_the_tag_for_nested_calls(sent):
    @usage.tagged("TUTOR_TITLE")
    async def work():
        gemini._report_text_usage(_ok_payload(), "m")

    await work()
    await _drain()

    assert sent[0]["feature"] == "TUTOR_TITLE"


def test_parse_response_exposes_thinking_tokens():
    res = gemini._parse_response(_ok_payload(), "m")

    assert (res.prompt_tokens, res.completion_tokens, res.thinking_tokens) == (100, 20, 300)


def test_estimate_tokens_is_about_four_chars_per_token():
    assert usage.estimate_tokens("a" * 400) == 100
    assert usage.estimate_tokens("") == 1
