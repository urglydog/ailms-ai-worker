"""UC30 mở rộng — nhớ lịch sử hội thoại + luôn bật Google Search Grounding trong CÙNG 1 lượt
gọi Gemini (BR-TUTOR-03 mở rộng) thay vì phân nhánh theo ngưỡng similarity — đã kiểm chứng
thực tế ngưỡng similarity KHÔNG phân biệt được "trùng chủ đề" và "chứa đúng câu trả lời".
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.providers.gemini import LlmResult
from app.providers.supabase_vector import MatchedSegment
from app.services import tutor_service

_CONTEXT = SimpleNamespace(
    lesson_title="Bai 1: Unity AI Assistant",
    source_language="en-US",
    duration_sec=600,
    course_title="Unity co ban",
    course_description="Khoa hoc lam game voi Unity va cac cong cu AI ho tro",
)


async def test_answer_always_enables_google_search_grounding():
    """Ngu canh THAT SU tra loi duoc (khong chi trung chu de) van phai bat grounding — de
    Gemini tu quyet dung hay khong theo system prompt, khong phan nhanh o tang Python."""
    segments = [MatchedSegment(segment_id=1, content="Noi dung lien quan", start_sec=65.0, end_sec=70.0, similarity=0.82)]
    generate_mock = AsyncMock(return_value=LlmResult(text="Ban nghi X co dung khong? [01:05]", model="m"))

    with patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=segments)), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(21, "Cai nay la gi?")

    assert result.cited_timestamps == [65]
    call = generate_mock.await_args
    assert call.kwargs.get("tools") == [{"google_search": {}}]
    assert "Noi dung lien quan" in call.args[0][-1]["parts"][0]["text"]  # ngu canh duoc dua vao prompt


async def test_answer_includes_topically_similar_but_non_answering_segments_as_context():
    """Ca ban lap lai dung tinh huong thuc te da phat hien: 'Unity AI Assistant co free khong?'
    khi Supabase tra ve doan noi ve CACH CAI DAT (trung chu de) chu khong noi ve gia ca — segments
    KHONG rong nhung van phai duoc coi la 'co the khong du', dua vao prompt de Gemini tu nhan ra."""
    topically_similar_but_irrelevant = [
        MatchedSegment(segment_id=1, content="huong dan cai dat Unity AI Assistant", start_sec=0.0, end_sec=10.0, similarity=0.78),
    ]
    generate_mock = AsyncMock(return_value=LlmResult(
        text="Video bai giang hien tai khong de cap van de nay. Minh da tim kiem tren mang: co, mien phi.",
        model="m",
    ))

    with patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=topically_similar_but_irrelevant)), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(21, "Unity AI Assistant co free khong?")

    # khong bia moc thoi gian cho cau tra loi tim tren web
    assert result.cited_timestamps == []
    call = generate_mock.await_args
    assert call.kwargs.get("tools") == [{"google_search": {}}]
    prompt_text = call.args[0][-1]["parts"][0]["text"]
    assert "huong dan cai dat Unity AI Assistant" in prompt_text  # ngu canh van duoc dua vao, khong bi bo qua
    assert "Unity co ban" in call.kwargs["system_instruction"]
    assert "KHONG dung Google Search" in call.kwargs["system_instruction"]


async def test_answer_without_any_matched_segments_still_calls_gemini_with_grounding():
    generate_mock = AsyncMock(return_value=LlmResult(
        text="Video bai giang hien tai khong de cap van de nay. Minh da tim kiem tren mang: co, mien phi.",
        model="m",
    ))

    with patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=[])), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(21, "Cau hoan toan khong lien quan bai giang")

    assert result.cited_timestamps == []
    call = generate_mock.await_args
    assert call.kwargs.get("tools") == [{"google_search": {}}]
    prompt_text = call.args[0][-1]["parts"][0]["text"]
    assert "khong tim thay doan transcript nao" in prompt_text.lower()


async def test_answer_includes_prior_history_as_multiturn_contents():
    """Cau hoi noi tiep kieu 'cau hoi tren la gi' phai thay duoc lich su trong `contents`."""
    generate_mock = AsyncMock(return_value=LlmResult(text="Cau hoi truoc la ve Unity AI Assistant.", model="m"))
    history = [
        {"sender": "USER", "content": "Unity AI Assistant co free khong?"},
        {"sender": "AI", "content": "Video khong de cap, minh da tim tren mang: co ban mien phi."},
    ]

    with patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=[])), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        await tutor_service.answer(21, "Cau hoi tren la gi?", history=history)

    contents = generate_mock.await_args.args[0]
    assert contents[0] == {"role": "user", "parts": [{"text": "Unity AI Assistant co free khong?"}]}
    assert contents[1] == {"role": "model", "parts": [{"text": "Video khong de cap, minh da tim tren mang: co ban mien phi."}]}
    assert contents[-1]["role"] == "user"
    assert "Cau hoi tren la gi?" in contents[-1]["parts"][0]["text"]


async def test_answer_with_attachments_addsInlineDataPartsAfterText():
    generate_mock = AsyncMock(return_value=LlmResult(text="Day la anh chup loi cu phap dong 5.", model="m"))
    attachment = tutor_service.Attachment(mime_type="image/png", data_base64="ZmFrZS1pbWFnZS1ieXRlcw==")

    with patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=[])), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        await tutor_service.answer(21, "Loi nay nghia la gi?", attachments=[attachment])

    contents = generate_mock.await_args.args[0]
    current_turn_parts = contents[-1]["parts"]
    assert current_turn_parts[0]["text"]  # phan text luon dung TRUOC
    assert current_turn_parts[1] == {"inlineData": {"mimeType": "image/png", "data": "ZmFrZS1pbWFnZS1ieXRlcw=="}}


async def test_generate_title_returns_trimmed_single_line():
    generate_mock = AsyncMock(return_value=LlmResult(text='"Hoi ve Unity AI Assistant"\n', model="m"))
    with patch("app.providers.gemini.generate", generate_mock):
        result = await tutor_service.generate_title("Unity AI Assistant co free khong?", "Co, mien phi mot phan.")

    assert result == "Hoi ve Unity AI Assistant"


async def test_generate_title_falls_back_when_gemini_fails():
    with patch("app.providers.gemini.generate", AsyncMock(side_effect=RuntimeError("boom"))):
        result = await tutor_service.generate_title("Cau hoi", "Tra loi")

    assert result == "Cuộc trò chuyện mới"
