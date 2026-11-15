"""translate_batch không bao giờ trả câu rỗng (job 30: Gemini bỏ sót dòng cuối -> TTS 0 byte)."""

from unittest.mock import AsyncMock, patch

from app.models import Segment
from app.services import translation


class _R:
    def __init__(self, text):
        self.text = text


async def test_missing_lines_are_retranslated_in_one_extra_call():
    segs = [Segment(seq=i, start=0.0, end=1.0, text=f"src{i}") for i in range(3)]
    gen = AsyncMock(side_effect=[
        _R('{"1": "A", "2": ""}'),           # dong 2 rong, dong 3 thieu
        _R('{"1": "B", "2": "C"}'),          # dich lai rieng 2 dong thieu
    ])
    with patch("app.providers.gemini.generate", gen):
        out = await translation.translate_batch(segs, "en", "vi-VN")
    assert out == ["A", "B", "C"]
    assert gen.await_count == 2


async def test_still_missing_falls_back_to_source_text():
    segs = [Segment(seq=1, start=0.0, end=1.0, text="hello")]
    gen = AsyncMock(side_effect=[_R("{}"), _R("{}")])
    with patch("app.providers.gemini.generate", gen):
        out = await translation.translate_batch(segs, "en", "vi-VN")
    assert out == ["hello"]
