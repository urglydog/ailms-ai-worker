"""UC30 mở rộng — nhớ lịch sử hội thoại + luôn bật Google Search Grounding trong CÙNG 1 lượt
gọi Gemini (BR-TUTOR-03 mở rộng) thay vì phân nhánh theo ngưỡng similarity — đã kiểm chứng
thực tế ngưỡng similarity KHÔNG phân biệt được "trùng chủ đề" và "chứa đúng câu trả lời".
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.http.backend_client import CourseLesson
from app.providers.gemini import LlmResult
from app.providers.supabase_vector import MatchedSegment
from app.services import tutor_service


def _seg(lesson_id: int, content: str, start_sec: float, end_sec: float = None, similarity: float = 0.8) -> MatchedSegment:
    """Fixture ngắn — `MatchedSegment` giờ bắt buộc `lesson_id` (UC30 mở rộng 13/09/2026, tìm
    kiếm xuyên khóa)."""
    return MatchedSegment(
        segment_id=1, lesson_id=lesson_id, content=content, start_sec=start_sec,
        end_sec=end_sec if end_sec is not None else start_sec + 5.0, similarity=similarity,
    )

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
    segments = [MatchedSegment(segment_id=1, lesson_id=21, content="Noi dung lien quan", start_sec=65.0, end_sec=70.0, similarity=0.82)]
    generate_mock = AsyncMock(return_value=LlmResult(text="Ban nghi X co dung khong? [01:05]", model="m"))

    with patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=segments)), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer_single_lesson(21,"Cai nay la gi?")

    assert result.cited_timestamps == [65]
    call = generate_mock.await_args
    assert call.kwargs.get("tools") == [{"google_search": {}}]
    assert "Noi dung lien quan" in call.args[0][-1]["parts"][0]["text"]  # ngu canh duoc dua vao prompt


async def test_answer_includes_topically_similar_but_non_answering_segments_as_context():
    """Ca ban lap lai dung tinh huong thuc te da phat hien: 'Unity AI Assistant co free khong?'
    khi Supabase tra ve doan noi ve CACH CAI DAT (trung chu de) chu khong noi ve gia ca — segments
    KHONG rong nhung van phai duoc coi la 'co the khong du', dua vao prompt de Gemini tu nhan ra."""
    topically_similar_but_irrelevant = [
        MatchedSegment(segment_id=1, lesson_id=21, content="huong dan cai dat Unity AI Assistant", start_sec=0.0, end_sec=10.0, similarity=0.78),
    ]
    generate_mock = AsyncMock(return_value=LlmResult(
        text="Video bai giang hien tai khong de cap van de nay. Minh da tim kiem tren mang: co, mien phi.",
        model="m",
    ))

    with patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=topically_similar_but_irrelevant)), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer_single_lesson(21,"Unity AI Assistant co free khong?")

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
        result = await tutor_service.answer_single_lesson(21,"Cau hoan toan khong lien quan bai giang")

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
        await tutor_service.answer_single_lesson(21, "Cau hoi tren la gi?", history=history)

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
        await tutor_service.answer_single_lesson(21, "Loi nay nghia la gi?", attachments=[attachment])

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


# ── UC30 mở rộng (13/09/2026) — Socratic Tutor tìm kiếm XUYÊN SUỐT mọi bài trong khóa ──

_COURSE_LESSONS = [
    CourseLesson(lesson_id=21, lesson_title="Bai 1", display_order=1),
    CourseLesson(lesson_id=22, lesson_title="Bai 2", display_order=2),
]


async def test_answer_prefersCurrentLesson_whenItAlreadyAnswers():
    """UU TIEN bai dang mo (13/09/2026, sua lan 2): bai dang mo (22) da du de tra loi (Gemini
    trich duoc moc [MM:SS] tu Buoc 1) -> dung NGAY ket qua nay, TUYET DOI khong tim tiep sang bai
    khac (`match_segments_by_lessons`/Buoc 2 KHONG DUOC GOI) — day la hanh vi UU TIEN nguoi dung
    yeu cau, tranh nhay bai khong can thiet khi bai dang mo van du."""
    current_lesson_segments = [_seg(22, "Noi dung tra loi ngay o bai dang mo", start_sec=51.0)]
    generate_mock = AsyncMock(return_value=LlmResult(text="Dap an: ... [00:51]", model="m"))
    course_wide_mock = AsyncMock()

    with patch("app.http.backend_client.get_course_lessons", AsyncMock(return_value=_COURSE_LESSONS)), \
         patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=current_lesson_segments)), \
         patch("app.providers.supabase_vector.match_segments_by_lessons", course_wide_mock), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(9, 22, "Cau hoi ma bai dang mo da tra loi duoc")

    assert result.context_lesson_id == 22
    assert result.cited_timestamps == [51]
    generate_mock.assert_awaited_once()  # chi 1 luot goi Gemini — khong co Buoc 2
    course_wide_mock.assert_not_awaited()


async def test_answer_fallsBackToOtherLessons_whenCurrentLessonHasNoAnswer():
    """Bai dang mo (22) THAT SU khong tra loi duoc (Buoc 1 khong trich moc nao) -> Buoc 2 tim
    tren CAC BAI CON LAI (khong gom lai bai 22 — da xac nhan khong co gi o do)."""
    generate_mock = AsyncMock(side_effect=[
        LlmResult(text="Video bai giang khong de cap, minh da tim tren mang: ...", model="m"),  # Buoc 1: that bai
        LlmResult(text="Tra loi: ... [21|00:10]", model="m"),  # Buoc 2: thanh cong o bai khac
    ])

    with patch("app.http.backend_client.get_course_lessons", AsyncMock(return_value=_COURSE_LESSONS)), \
         patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=[])), \
         patch("app.providers.supabase_vector.match_segments_by_lessons", AsyncMock(return_value=[])) as match_mock, \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(9, 22, "Cau hoi bat ky")

    assert generate_mock.await_count == 2
    match_mock.assert_awaited_once()
    assert match_mock.await_args.args[0] == [21]  # KHONG gom lai bai 22 (da biet khong co gi)
    assert result.cited_timestamps == [10]
    assert result.context_lesson_id == 21


async def test_answer_citesLessonDifferentFromCurrentlyOpenOne_andJumpsToIt():
    """Dung Bai 10 (id=22 trong fixture) hoi 1 cau CHUNG CHUNG, bai dang mo khong tra loi duoc,
    dap an nam o Bai 1 (id=21) phut 1:30 — Gemini duoc cung cap doan ngu canh cua Bai 1 kem san
    [21|01:30], trich lai dung dinh dang do -> `cited_timestamps`/`context_lesson_id` phai tro ve
    DUNG bai 21, khong phai bai dang mo (22). Day chinh la kich ban nguoi dung yeu cau mo rong."""
    segments = [_seg(21, "Noi dung tra loi cau hoi", start_sec=90.0)]  # Bai 1, phut 1:30
    generate_mock = AsyncMock(side_effect=[
        LlmResult(text="Video bai giang khong de cap, minh da tim tren mang: ...", model="m"),  # Buoc 1: that bai
        LlmResult(text="Dap an nam o [21|01:30]: ...", model="m"),  # Buoc 2
    ])

    with patch("app.http.backend_client.get_course_lessons", AsyncMock(return_value=_COURSE_LESSONS)), \
         patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=[])), \
         patch("app.providers.supabase_vector.match_segments_by_lessons", AsyncMock(return_value=segments)), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(9, 22, "Cau hoi ma dap an o bai khac")

    assert result.context_lesson_id == 21
    assert result.cited_timestamps == [90]
    prompt_text = generate_mock.await_args_list[-1].args[0][-1]["parts"][0]["text"]
    assert "[21|01:30]" in prompt_text  # ngu canh dua cho Gemini da danh dau san lessonId


async def test_answer_multipleCitationsAcrossLessons_primaryIsMostCited():
    """Buoc 2 tra loi trich dan tu 2 bai khac nhau — `context_lesson_id` (chi con y nghia tham
    khao/hien thi, xem docblock dau `tutor_service.py`) phai la bai duoc trich NHIEU LAN hon."""
    generate_mock = AsyncMock(side_effect=[
        LlmResult(text="Video bai giang khong de cap, minh da tim tren mang: ...", model="m"),  # Buoc 1: that bai
        LlmResult(text="Xem [21|00:10] va [21|00:20], ngoai ra con [22|00:05].", model="m"),  # Buoc 2
    ])

    with patch("app.http.backend_client.get_course_lessons", AsyncMock(return_value=_COURSE_LESSONS)), \
         patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=[])), \
         patch("app.providers.supabase_vector.match_segments_by_lessons", AsyncMock(return_value=[])), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(9, 22, "Cau hoi bat ky")

    assert result.context_lesson_id == 21
    assert result.cited_timestamps == [10, 20, 5]


async def test_answer_noCitationsAnywhereInCourse_fallsBackToCurrentLessonId():
    """Ca Buoc 1 (bai dang mo) lan Buoc 2 (cac bai con lai) deu di huong tim web (khong trich dan
    bai giang nao) -> `context_lesson_id` roi ve bai HOC VIEN DANG MO, khong phai None/loi."""
    generate_mock = AsyncMock(return_value=LlmResult(
        text="Video bai giang khong de cap, minh da tim tren mang: ...", model="m",
    ))

    with patch("app.http.backend_client.get_course_lessons", AsyncMock(return_value=_COURSE_LESSONS)), \
         patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments", AsyncMock(return_value=[])), \
         patch("app.providers.supabase_vector.match_segments_by_lessons", AsyncMock(return_value=[])), \
         patch("app.providers.gemini.generate_conversation", generate_mock):
        result = await tutor_service.answer(9, 22, "Cau hoi ngoai chu de")

    assert generate_mock.await_count == 2
    assert result.context_lesson_id == 22
    assert result.cited_timestamps == []


async def test_answer_singleLessonCourse_stillSearchesThatOneLesson():
    with patch("app.http.backend_client.get_course_lessons", AsyncMock(return_value=[_COURSE_LESSONS[0]])), \
         patch("app.http.backend_client.get_tutor_context", AsyncMock(return_value=_CONTEXT)), \
         patch("app.providers.gemini.embed_content", AsyncMock(return_value=[0.1, 0.2])), \
         patch("app.providers.supabase_vector.match_segments_by_lessons", AsyncMock(return_value=[])) as match_mock, \
         patch("app.providers.gemini.generate_conversation", AsyncMock(return_value=LlmResult(text="[21|00:05]", model="m"))):
        result = await tutor_service.answer(9, 21, "Cau hoi bat ky")

    assert match_mock.await_args.args[0] == [21]
    assert result.context_lesson_id == 21
