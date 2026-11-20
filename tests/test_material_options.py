"""Số lượng / độ khó / mức chi tiết trong form tạo học liệu phải thật sự đi vào prompt (BR-MAT-05)."""

from unittest.mock import patch

import pytest

from app.providers.gemini import LlmResult
from app.services import material_options as mo
from app.tasks import material


def _result(text: str) -> LlmResult:
    return LlmResult(text=text, model="gemini-x", prompt_tokens=1, completion_tokens=1, thinking_tokens=0)


def test_target_counts_follow_the_form_labels_for_the_whole_course():
    assert [mo.target_count("QUIZ", q) for q in ("FEWER", "STANDARD", "MORE")] == [10, 20, 30]
    assert [mo.target_count("FLASHCARD", q) for q in ("FEWER", "STANDARD", "MORE")] == [10, 20, 30]


def test_narrower_scope_scales_by_lesson_share_with_floors():
    ratio = mo.scope_ratio(1, 4)
    assert ratio == 0.25
    assert mo.target_count("QUIZ", "STANDARD", ratio) == 5          # 20 × 0.25 = 5 (đúng sàn)
    assert mo.target_count("QUIZ", "FEWER", ratio) == 5             # 2,5 → sàn 5
    assert mo.target_count("FLASHCARD", "STANDARD", ratio) == 10    # 5 → sàn 10
    assert mo.target_count("QUIZ", "MORE", mo.scope_ratio(3, 4)) == 22  # 30 × 0.75 = 22,5 → 22 (làm tròn về chẵn)


def test_missing_or_unknown_values_keep_the_old_behaviour():
    assert mo.target_count("QUIZ", None) is None
    assert mo.target_count("QUIZ", "WEIRD") is None
    assert mo.quiz_clauses(None, None) == []
    assert mo.flashcard_clauses(None) == []
    assert mo.mindmap_depth_line(None) is None
    assert mo.scope_ratio(3, None) == 1.0
    assert mo.scope_ratio(0, 5) == 1.0
    assert mo.scope_ratio(9, 3) == 1.0


def test_difficulty_levels_give_different_instructions():
    texts = {d: mo.quiz_clauses(None, d)[0] for d in ("EASY", "MEDIUM", "HARD")}
    assert len(set(texts.values())) == 3
    assert "KHONG hoi dinh nghia" in texts["HARD"]


@pytest.mark.asyncio
async def test_quiz_prompt_contains_count_and_difficulty():
    seen: list[str] = []

    async def fake(prompt, **kw):
        seen.append(prompt)
        return _result('[{"content":"q","options":["a","b","c","d"],"correct_answer":"a","topic_tag":"t","video_timestamp":1}]')

    with patch.object(material.gemini, "generate", side_effect=fake):
        await material._generate_quizzes("noi dung", "ja-JP", "MORE", "HARD", 1.0)

    assert "khoang 30 cau hoi" in seen[0]
    assert "MUC DO KHO: KHO" in seen[0]
    assert "6. SO LUONG" in seen[0] and "7. MUC DO KHO" in seen[0]


@pytest.mark.asyncio
async def test_quiz_and_flashcard_prompts_stay_unchanged_without_options():
    seen: list[str] = []

    async def fake(prompt, **kw):
        seen.append(prompt)
        if "Quiz" in prompt:
            return _result('[{"content":"q","options":["a","b","c","d"],"correct_answer":"a","topic_tag":"t","video_timestamp":1}]')
        return _result('[{"front_text":"f","back_text":"b"}]')

    with patch.object(material.gemini, "generate", side_effect=fake):
        await material._generate_quizzes("nd", "vi-VN")
        await material._generate_flashcards("nd", "vi-VN")

    assert "SO LUONG" not in seen[0] and "MUC DO KHO" not in seen[0]
    assert "SO LUONG" not in seen[1]


@pytest.mark.asyncio
async def test_flashcard_prompt_scales_with_scope():
    seen: list[str] = []

    async def fake(prompt, **kw):
        seen.append(prompt)
        return _result('[{"front_text":"f","back_text":"b"}]')

    with patch.object(material.gemini, "generate", side_effect=fake):
        await material._generate_flashcards("nd", "vi-VN", "STANDARD", 0.25)
        await material._generate_flashcards("nd", "vi-VN", "MORE", 1.0)

    assert "khoang 10 the" in seen[0]
    assert "khoang 30 the" in seen[1]


@pytest.mark.asyncio
async def test_mindmap_depth_follows_the_detail_level():
    seen: list[str] = []

    async def fake(prompt, **kw):
        seen.append(prompt)
        return _result("flowchart TD\nA-->B")

    with patch.object(material.gemini, "generate", side_effect=fake):
        await material._generate_mindmap("nd", "vi-VN", "FEWER")
        await material._generate_mindmap("nd", "vi-VN", "MORE")
        await material._generate_mindmap("nd", "vi-VN")

    assert "toi da 3 cap" in seen[0]
    assert "toi da 5 cap, chi tiet" in seen[1]
    assert "toi da 4-5 cap" in seen[2]
