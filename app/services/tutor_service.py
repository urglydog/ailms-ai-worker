"""UC30 — Socratic AI Tutor: RAG (Supabase Vector) + Gemini, HTTP đồng bộ.

  · BR-TUTOR-01 — KHÔNG đưa đáp án trực tiếp/mã nguồn hoàn chỉnh KHI ngữ cảnh bài giảng
    thật sự chứa câu trả lời. Chỉ 1-2 câu hỏi gợi mở. Luận điểm cốt lõi của đề tài, vi
    phạm là phá vỡ mục tiêu nghiên cứu. KHÔNG áp dụng khi Gemini tự nhận ra ngữ cảnh
    không đủ và chuyển sang tìm kiếm web (mục BR-TUTOR-03 mở rộng bên dưới) — lúc đó
    trả lời trực tiếp câu hỏi tra cứu thông tin, không phải bài tập cần gợi mở.
  · BR-TUTOR-02 — mọi phản hồi DỰA TRÊN kiến thức bài giảng BẮT BUỘC kèm ≥1 mốc thời
    gian dạng `[MM:SS]` (Gemini được yêu cầu xuất đúng định dạng này trong prompt).
  · BR-TUTOR-03 (mở rộng) — GỘP 1 LƯỢT GỌI DUY NHẤT thay vì 2 nhánh tách rời theo ngưỡng
    similarity: luôn đính kèm cả ngữ cảnh transcript (nếu Supabase Vector tìm được) LẪN
    công cụ Google Search Grounding trong CÙNG 1 lần gọi, để chính Gemini tự quyết ngữ
    cảnh có thật sự trả lời được câu hỏi hay không — KHÔNG dựa vào ngưỡng
    `settings.rag_min_similarity` để quyết định nhánh.
    Lý do đổi từ thiết kế "2 nhánh theo ngưỡng" ban đầu: đã kiểm chứng thực tế — độ
    tương đồng vector đo MỨC TRÙNG CHỦ ĐỀ, không đo CÓ CHỨA ĐÚNG SỰ KIỆN ĐƯỢC HỎI hay
    không. Ví dụ thật: hỏi "Unity AI Assistant có free không?" cho bài giảng hướng dẫn
    cài đặt Unity AI Assistant — Supabase trả về 3 đoạn similarity 0.73-0.78 (đều > 0.7)
    nhưng KHÔNG đoạn nào nói về giá cả, chỉ trùng tên công cụ. Nếu tách nhánh theo ngưỡng
    như thiết kế cũ, câu hỏi này sẽ luôn rơi vào nhánh Socratic (vì luôn có đoạn > 0.7 do
    chủ đề được nhắc nhiều lần trong bài), không bao giờ tới được nhánh tìm web dù ngữ
    cảnh rõ ràng không đủ. Gộp 1 lượt vẫn giữ đúng chi phí ban đầu (không thêm request
    phân loại riêng) — guard-rail chủ đề nằm trong system prompt vì bản thân Google
    Search Grounding không tự chặn theo chủ đề.
  · BR-TUTOR-04 — tối đa `settings.rag_top_k` đoạn ngữ cảnh, ngưỡng `settings.rag_min_similarity`
    (giờ chỉ còn ý nghĩa "đoạn nào đủ liên quan để ĐƯA VÀO ngữ cảnh", không còn quyết định nhánh).

Nhớ hội thoại (UC30 mở rộng): `answer()` nhận thêm `history` — vài lượt gần nhất của
phiên chat (be/ tự cắt tối đa `HISTORY_LIMIT` lượt trước khi gửi sang) — dựng thành
`contents` đa lượt cho Gemini, để trả lời được câu hỏi nối tiếp kiểu "câu hỏi trên là gì?".

Phiên chat pham vi khoa hoc (06/09/2026, UC30 mo rong): truoc day 1 phien chat luon gan cung 1
`lesson_id`. Gio be/ dung chung 1 danh sach lich su cho ca khoa hoc, bai hoc dang mo chi con la
`current_lesson_id` truyen theo TUNG luot hoi.

Tim kiem XUYEN SUOT khoa hoc (13/09/2026, UC30 mo rong tiep): ban dau (06/09/2026) `answer()` goi
1 luot Gemini RIENG chi de "doan" xem cau hoi dang hoi ve bai nao (dua vao TEN bai hoc) roi MOI tim
noi dung trong DUNG 1 bai do (`resolve_target_lesson`) — bo HAN thiet ke nay vi qua mong manh: hoc
vien hoi 1 cau CHUNG CHUNG (khong nhac ten/so bai nao) nhung dap an lai nam o 1 bai KHAC bai dang
mo (vi du dang o Bai 10, hoi ve khai niem da giang o Bai 1 phut 1:30) se luon bi doan sai ve bai
dang mo, khong bao gio voi toi duoc noi dung that su. Thay bang tim kiem vector THAT SU tren TOAN
BO cac bai trong khoa CUNG LUC (`supabase_vector.match_segments_by_lessons`) — moi doan tra ve tu
mang theo dung `lesson_id` cua no, khong can doan truoc nua. Re hon thiet ke cu: bot han 1 luot goi
Gemini "phan loai" (giam tu 3 xuong 2 luot goi/cau hoi: embed cau hoi + sinh cau tra loi).

He qua: 1 cau tra loi gio co the trich dan tu NHIEU bai khac nhau cung luc, nen khong the dung 1
field `context_lesson_id` DUY NHAT cho ca cau tra loi nhu truoc (kieu cu chi ho tro dung 1 bai/cau
tra loi). Giai phap: MOI moc thoi gian Gemini trich tu mang theo LUON id bai hoc cua no ngay trong
van ban `[lessonId|MM:SS]` (thay vi `[MM:SS]` truoc day) — khong can doi kieu du lieu
`cited_timestamps`/`context_lesson_id` gui ve be/ (be/ chi pass-through, khong doc dinh dang ben
trong chuoi cau tra loi) — chi FE (`MarkdownRenderer.tsx`) can doc them id bai hoc tu dinh dang moi
nay de tua dung video + tu dieu huong sang dung bai khi khac bai dang mo (xem `learn/[lessonId]/page.tsx`).
`context_lesson_id` gui ve be/ gio la BAI DUOC TRICH DAN NHIEU NHAT (hoac bai dang mo neu khong
trich dan bai nao) — chi con y nghia "tham khao/hien thi", KHONG con dung de dieu huong nua.

`answer_single_lesson()` giu nguyen hanh vi CU (1 lesson_id co dinh, khong tim xuyen khoa, dinh
dang trich dan van la `[MM:SS]` khong doi) — chi con dung cho luong giai thich cau hoi trac nghiem
(`com.lms.material.service.QuizService`, goi thang `/api/v1/tutor/ask` voi `lesson_id=-1`, khong
qua `TutorService.ask` cua Socratic Tutor — luon dung DUNG 1 bai, khong co gi de tim xuyen khoa).

UU TIEN bai dang mo (13/09/2026, sua lan 2): ban dau tim xuyen khoa CUNG LUC (khong uu tien bai
nao) co nhuoc diem — hoc vien dang o dung bai co cau tra loi van co the bi nhay sang bai KHAC chi
vi 1 doan o bai do tinh co co diem similarity nhinh hon 1 chut, gay trai nghiem kho chiu (dang xem
dung cho van bi keo di noi khac). Sua lai thanh 2 BUOC:
  Buoc 1 — thu tra loi trong DUNG bai dang mo TRUOC (goi nguyen `_answer_for_lesson` cu, dinh dang
  `[MM:SS]` khong doi). Neu Gemini THAT SU tra loi duoc tu bai do (ket qua co it nhat 1 moc trich
  dan) — DUNG NGAY, tra ve luon, KHONG tim tiep sang bai khac. Tin hieu "tra loi duoc hay khong"
  o day la CHINH GEMINI tu quyet dinh (co trich duoc moc thoi gian hay khong), KHONG phai nguong
  similarity Python tu tinh — giu dung triet ly da kiem chung o BR-TUTOR-03 (nguong similarity
  KHONG phan biet duoc "trung chu de" va "co dung cau tra loi", chi Gemini doc that su moi biet).
  Buoc 2 — CHI khi Buoc 1 khong trich duoc moc nao (bai dang mo THAT SU khong lien quan) moi tim
  tiep tren CAC BAI CON LAI trong khoa (khong gom lai bai dang mo — da xac nhan khong co gi o do)
  bang `_answer_for_course`, dung dinh dang `[lessonId|MM:SS]` nhu truoc.
Chi phi: truong hop pho bien (bai dang mo da du de tra loi) van chi ton 1 luot goi Gemini generate
nhu cu; chi ton THEM 1 luot (embed + generate cho Buoc 2) khi bai dang mo that su khong co gi —
dung luc can tim xuyen khoa nhat.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.http import backend_client
from app.providers import gemini, supabase_vector
from app.providers.base import ProviderInvalidResponse

_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):([0-5]?\d)\]")
#: Dinh dang moi (13/09/2026) — dung rieng cho `_answer_for_course` (tim xuyen khoa), mang them
#: lessonId ngay trong van ban vi 1 cau tra loi gio co the trich dan nhieu bai khac nhau cung luc.
_LESSON_TIMESTAMP_RE = re.compile(r"\[(\d+)\|(\d{1,3}):([0-5]?\d)\]")


@dataclass(frozen=True)
class TutorAnswer:
    answer: str
    cited_timestamps: list[int]
    token_used: int
    #: Bai hoc duoc trich dan NHIEU NHAT trong cau tra loi (hoac bai dang mo neu khong trich dan
    #: bai nao) — None chi cho luong cu (giai thich quiz, khong gan bai hoc nao). Chi con y nghia
    #: "tham khao/hien thi mac dinh", KHONG con dung de dieu huong tua video (xem docblock dau
    #: file) — FE doc lessonId truc tiep tu dinh dang `[lessonId|MM:SS]` trong van ban de tua.
    context_lesson_id: int | None = None


def _format_mmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _extract_timestamps(text: str) -> list[int]:
    """Trích các mốc `[MM:SS]` trong câu trả lời của Gemini thành danh sách giây
    nguyên, KHÔNG trùng lặp, giữ đúng thứ tự xuất hiện (BR-TUTOR-02). Câu trả lời đi
    theo hướng tìm web (không dựa vào bài giảng) sẽ tự nhiên không có mốc nào để trích.
    """
    seen: dict[int, None] = {}
    for m, s in _TIMESTAMP_RE.findall(text):
        seconds = int(m) * 60 + int(s)
        seen.setdefault(seconds, None)
    return list(seen.keys())


def _build_history_contents(history: list[dict]) -> list[dict]:
    """`sender` khớp `ChatMessage.sender` bên be/ (`"USER"`/`"AI"`) -> role Gemini
    (`"user"`/`"model"`). Đã ở đúng thứ tự cũ -> mới (be/ tự đảo trước khi gửi)."""
    return [
        {"role": "model" if turn.get("sender") == "AI" else "user", "parts": [{"text": turn.get("content", "")}]}
        for turn in history
    ]


def _build_system_instruction(
    lesson_title: str, course_title: str, course_description: str, language: str | None = None,
    *, multi_lesson: bool = False,
) -> str:
    topic = course_description or course_title

    lang_rule = ""
    if language:
        lang_rule = f"\nCRITICAL INSTRUCTION: You MUST write your ENTIRE response in the language corresponding to the language code '{language}'. DO NOT use Vietnamese or English unless it is the requested language."

    if multi_lesson:
        # UC30 mo rong (13/09/2026) — ngu canh gio co the gom doan tu NHIEU bai hoc khac nhau
        # trong cung khoa hoc, moi doan da duoc danh dau san [lessonId|MM:SS] (xem
        # `_build_prompt_multi`) — Gemini CHI can copy nguyen dinh dang do, khong tu bia/doi id.
        citation_rule = (
            "BAT BUOC trich it nhat 1 moc thoi gian, COPY NGUYEN VAN dinh dang [lessonId|MM:SS] "
            "DA CO SAN o dau moi doan ngu canh duoc cung cap (vi du doan ngu canh ghi \"[12|01:30] "
            "...\" thi trich lai DUNG \"[12|01:30]\", KHONG duoc doi lessonId, KHONG duoc tu ghep "
            "lessonId voi mot moc thoi gian khac, KHONG duoc bia moc khong co trong ngu canh."
        )
    else:
        citation_rule = (
            "BAT BUOC trich it nhat 1 moc thoi gian dung dinh dang [MM:SS] tu ngu canh duoc cung "
            "cap, KHONG duoc bia moc khong co trong ngu canh."
        )

    return f"""Ban la Gia su AI theo phuong phap Socratic cho khoa hoc "{course_title}" (chu de:
{topic}), dang ho tro bai giang "{lesson_title}".{lang_rule}

Moi luot hoi, ban co the duoc cung cap:
- NGU CANH BAI GIANG: cac doan transcript ma he thong tim thay LIEN QUAN CHU DE cau hoi —
  CHU Y: chi la lien quan chu de, KHONG chac chan da chua dung cau tra loi hoc vien can.
- CONG CU Google Search: dung khi ngu canh khong du de tra loi.
- TEP DINH KEM (neu co): hinh anh/tai lieu/ma nguon hoc vien gui kem cau hoi de hoi ve chinh
  noi dung do (vi du: anh chup loi bao code, so do, tai lieu tham khao lien quan bai hoc).

QUY TAC BAT BUOC — xet theo dung thu tu:
1. Neu NGU CANH BAI GIANG o tren THAT SU chua noi dung tra loi duoc cau hoi (khong chi
   nhac ten/chu de lien quan) -> tra loi theo phong cach Socratic: TUYET DOI KHONG dua
   dap an truc tiep, loi giai hoan chinh hay ma nguon day du (du hoc vien yeu cau thang
   cung tu choi kieu nay) — chi dat lai 1-2 cau hoi goi mo de hoc vien tu suy luan. {citation_rule}
2. Neu NGU CANH BAI GIANG KHONG chua cau tra loi (du co nhac ten chu de, hoac khong co
   doan nao duoc cung cap), nhung cau hoi (hoac tep dinh kem) lien quan toi chu de khoa
   hoc, cong nghe/cong cu duoc nhac toi trong khoa hoc, hoac kien thuc nen tang huu ich
   cho viec hoc (vi du: hoi ve 1 cong cu/phan mem lien quan, phien ban moi, gia ca, tinh
   nang, giai thich loi trong anh chup code lien quan bai hoc...) -> dung Google Search
   neu can, TRA LOI TRUC TIEP (khong can goi mo, khong can moc thoi gian), MO DAU cau tra
   loi bang: "Video bai giang hien tai khong de cap van de nay. Minh da tim kiem tren
   mang: ..." (bo qua cau mo dau nay neu cau tra loi den tu VIEC PHAN TICH TEP DINH KEM,
   khong phai tu tim kiem web).
3. Neu cau hoi HOAN TOAN khong lien quan toi giao duc/chu de khoa hoc (vi du: thoi tiet,
   tin tuc, giai tri, chuyen ca nhan...), HOAC neu TEP DINH KEM khong lien quan gi toi noi
   dung hoc tap/khoa hoc (anh phong canh, do vat, nguoi khong lien quan bai giang, tai
   lieu ngoai chu de...) -> tu choi lich su, GIAI THICH RO LY DO (vi du: "Hinh anh nay
   khong lien quan toi noi dung khoa hoc nen minh chua the ho tro duoc"), huong hoc vien
   quay lai noi dung bai hoc. KHONG dung Google Search, KHONG phan tich noi dung tep
   trong truong hop nay du tep do co the phan tich duoc ve mat ky thuat.
4. Neu hoc vien hoi tiep ve luot truoc ("cau hoi tren la gi", "y ban vua roi la sao"...),
   dua vao LICH SU hoi thoai ben tren de tra loi dung, khong noi "khong nho".
5. Dinh dang cau tra loi bang Markdown de hoc vien de doc: dung **in dam** cho tu khoa
   quan trong, danh sach gach dau dong (-) hoac danh so (1. 2. 3.) khi liet ke nhieu y,
   tieu de nho (###) khi can chia thanh nhieu phan, bang Markdown (cot | cot) khi so
   sanh/doi chieu nhieu muc, va CHEN emoji phu hop de lam noi bat y chinh (vi du: ✅ ⚠️
   💡 📌 🎯 🔧). CHI dinh dang khi cau tra loi du dai de can cau truc — cau tra loi
   Socratic 1-2 cau hoi goi mo (quy tac 1) thi KHONG can dinh dang phuc tap.
6. Tra loi ngan gon, giong dieu than thien, khuyen khich."""


def _build_prompt(question: str, segments: list[supabase_vector.MatchedSegment], has_attachments: bool) -> str:
    if segments:
        context = "\n".join(f"- [{_format_mmss(s.start_sec)}] {s.content}" for s in segments)
    else:
        context = "(He thong khong tim thay doan transcript nao lien quan chu de cau hoi nay.)"
    attachment_note = (
        "\n## Tep dinh kem\n(Hoc vien co gui kem tep — xem noi dung tep ngay trong luot nay de danh gia theo quy tac 2/3.)\n"
        if has_attachments else ""
    )
    return f"""## Ngu canh bai giang (cac doan lien quan chu de nhat, CO THE khong chua cau tra loi)
{context}
{attachment_note}
## Cau hoi cua hoc vien
{question}

Tra loi theo dung 6 quy tac da neu, xet dung thu tu tu quy tac 1."""


def _build_prompt_multi(
    question: str, segments: list[supabase_vector.MatchedSegment], lesson_titles: dict[int, str],
    has_attachments: bool,
) -> str:
    """UC30 mo rong (13/09/2026) — nhu `_build_prompt` nhung ngu canh gio co the gom nhieu bai hoc
    khac nhau trong cung khoa hoc; moi doan danh dau san `[lessonId|MM:SS]` + ten bai de Gemini
    COPY NGUYEN VAN khi trich dan (xem quy tac 1 trong `_build_system_instruction`)."""
    if segments:
        context = "\n".join(
            f'- [{s.lesson_id}|{_format_mmss(s.start_sec)}] (Bai: "{lesson_titles.get(s.lesson_id, "?")}") {s.content}'
            for s in segments
        )
    else:
        context = "(He thong khong tim thay doan transcript nao lien quan chu de cau hoi nay trong ca khoa hoc.)"
    attachment_note = (
        "\n## Tep dinh kem\n(Hoc vien co gui kem tep — xem noi dung tep ngay trong luot nay de danh gia theo quy tac 2/3.)\n"
        if has_attachments else ""
    )
    return f"""## Ngu canh bai giang (cac doan lien quan chu de nhat TRONG CA KHOA HOC, CO THE tu nhieu bai khac nhau, CO THE khong chua cau tra loi)
{context}
{attachment_note}
## Cau hoi cua hoc vien
{question}

Tra loi theo dung 6 quy tac da neu, xet dung thu tu tu quy tac 1."""


def _extract_lesson_citations(text: str) -> list[tuple[int, int]]:
    """Trich cac moc `[lessonId|MM:SS]` thanh danh sach (lessonId, giay), KHONG trung lap, giu
    dung thu tu xuat hien (ban `_answer_for_course` cua BR-TUTOR-02)."""
    seen: dict[tuple[int, int], None] = {}
    for lesson_id, m, s in _LESSON_TIMESTAMP_RE.findall(text):
        key = (int(lesson_id), int(m) * 60 + int(s))
        seen.setdefault(key, None)
    return list(seen.keys())


@dataclass(frozen=True)
class Attachment:
    """1 tep hoc vien gui kem cau hoi — `data_base64` la noi dung tep DA ma hoa base64,
    gui thang cho Gemini duoi dang `inlineData` (BR-TUTOR-03 mo rong: cung 1 luot goi,
    khong can lenh phan loai rieng — xem `_build_system_instruction` quy tac 3)."""

    mime_type: str
    data_base64: str


async def _answer_for_lesson(
    lesson_id: int, question: str, history: list[dict] | None, attachments: list[Attachment] | None,
    language: str | None,
) -> TutorAnswer:
    """Pipeline RAG + Gemini goc (khong doi tu truoc 06/09/2026), chay cho DUNG 1 lesson_id co
    dinh, dinh dang trich dan van la `[MM:SS]` (khong co lessonId). Ke tu 13/09/2026, `answer()`
    (Socratic Tutor chinh) khong con goi ham nay nua — chuyen sang `_answer_for_course` (tim xuyen
    khoa). Chi con dung boi `answer_single_lesson()` (luong giai thich cau hoi trac nghiem)."""
    context = await backend_client.get_tutor_context(lesson_id)
    history_contents = _build_history_contents(history or [])

    query_vector = await gemini.embed_content(question)
    segments = await supabase_vector.match_segments(lesson_id, query_vector)

    attachments = attachments or []
    current_parts: list[dict] = [{"text": _build_prompt(question, segments, bool(attachments))}]
    for att in attachments:
        current_parts.append({"inlineData": {"mimeType": att.mime_type, "data": att.data_base64}})

    contents = history_contents + [{"role": "user", "parts": current_parts}]
    result = await gemini.generate_conversation(
        contents,
        system_instruction=_build_system_instruction(
            context.lesson_title, context.course_title, context.course_description, language
        ),
        # Luon bat san — Gemini tu quyet co can dung hay khong dua theo quy tac 1-3 trong
        # system prompt, khong con phan nhanh o tang Python theo nguong similarity.
        tools=[{"google_search": {}}],
    )

    if isinstance(result, gemini.FunctionCall):
        raise ProviderInvalidResponse("Gemini tra ve FunctionCall ngoai du kien cho Tutor")

    return TutorAnswer(
        answer=result.text.strip(),
        cited_timestamps=_extract_timestamps(result.text),
        token_used=result.total_tokens,
        context_lesson_id=lesson_id,
    )


async def _answer_for_course(
    course_lessons: list[backend_client.CourseLesson], current_lesson_id: int, question: str,
    history: list[dict] | None, attachments: list[Attachment] | None, language: str | None,
) -> TutorAnswer:
    """UC30 mo rong (13/09/2026) — tim kiem vector tren TOAN BO cac bai trong khoa CUNG LUC (xem
    docblock dau file ve ly do thay the `resolve_target_lesson` + `_answer_for_lesson` cu)."""
    current_lesson = next((l for l in course_lessons if l.lesson_id == current_lesson_id), None)
    current_title = current_lesson.lesson_title if current_lesson else ""
    context = await backend_client.get_tutor_context(current_lesson_id)
    history_contents = _build_history_contents(history or [])

    lesson_ids = [l.lesson_id for l in course_lessons] or [current_lesson_id]
    lesson_titles = {l.lesson_id: l.lesson_title for l in course_lessons}
    query_vector = await gemini.embed_content(question)
    segments = await supabase_vector.match_segments_by_lessons(lesson_ids, query_vector)

    attachments = attachments or []
    current_parts: list[dict] = [{"text": _build_prompt_multi(question, segments, lesson_titles, bool(attachments))}]
    for att in attachments:
        current_parts.append({"inlineData": {"mimeType": att.mime_type, "data": att.data_base64}})

    contents = history_contents + [{"role": "user", "parts": current_parts}]
    result = await gemini.generate_conversation(
        contents,
        system_instruction=_build_system_instruction(
            current_title or context.lesson_title, context.course_title, context.course_description,
            language, multi_lesson=True,
        ),
        tools=[{"google_search": {}}],
    )

    if isinstance(result, gemini.FunctionCall):
        raise ProviderInvalidResponse("Gemini tra ve FunctionCall ngoai du kien cho Tutor")

    citations = _extract_lesson_citations(result.text)
    # "Bai duoc trich dan nhieu nhat" — chi la gia tri tham khao/hien thi mac dinh gui ve be/, FE
    # khong con dung field nay de dieu huong nua (xem docblock dau file va TutorAnswer).
    if citations:
        lesson_counts = Counter(lesson_id for lesson_id, _ in citations)
        primary_lesson_id = lesson_counts.most_common(1)[0][0]
    else:
        primary_lesson_id = current_lesson_id

    return TutorAnswer(
        answer=result.text.strip(),
        cited_timestamps=[seconds for _, seconds in citations],
        token_used=result.total_tokens,
        context_lesson_id=primary_lesson_id,
    )


async def answer(
    course_id: int, current_lesson_id: int, question: str, history: list[dict] | None = None,
    attachments: list[Attachment] | None = None, language: str | None = None,
) -> TutorAnswer:
    """UC30 mo rong (13/09/2026, sua lan 2) — UU TIEN bai dang mo, xem docblock dau file.
    Buoc 1: thu tra loi trong DUNG bai dang mo (`_answer_for_lesson` cu) — neu Gemini trich duoc
    it nhat 1 moc thoi gian tu do (nghia la THAT SU tra loi duoc), dung ngay, KHONG tim tiep.
    Buoc 2: chi khi Buoc 1 khong trich duoc moc nao moi tim tren CAC BAI CON LAI trong khoa
    (`_answer_for_course`, khong gom lai bai dang mo — da xac nhan khong co gi o do).
    """
    course_lessons = await backend_client.get_course_lessons(course_id)

    if len(course_lessons) > 1:
        current_result = await _answer_for_lesson(current_lesson_id, question, history, attachments, language)
        if current_result.cited_timestamps:
            return current_result
        other_lessons = [l for l in course_lessons if l.lesson_id != current_lesson_id]
    else:
        other_lessons = course_lessons

    return await _answer_for_course(other_lessons, current_lesson_id, question, history, attachments, language)


async def answer_single_lesson(
    lesson_id: int, question: str, history: list[dict] | None = None, attachments: list[Attachment] | None = None,
    language: str | None = None,
) -> TutorAnswer:
    """Đường CŨ (không đổi hành vi) — 1 `lesson_id` cố định, không phân loại/không RAG toàn
    khóa. Chỉ còn dùng cho luồng giải thích câu hỏi trắc nghiệm (xem docblock đầu file)."""
    return await _answer_for_lesson(lesson_id, question, history, attachments, language)


_FALLBACK_TITLE = "Cuộc trò chuyện mới"


async def generate_title(question: str, answer: str) -> str:
    """UC30 mở rộng — đặt tên ngắn cho 1 cuộc trò chuyện dựa trên lượt hỏi-đáp ĐẦU TIÊN, giống
    ChatGPT/Gemini tự gợi ý tiêu đề. Chỉ 1 lượt gọi Gemini đơn giản (không cần lịch sử, không
    cần RAG/grounding) — be/ chỉ gọi hàm này ĐÚNG 1 LẦN mỗi phiên mới, không phải mỗi tin nhắn.
    """
    prompt = f"""Cau hoi cua hoc vien: {question}
Cau tra loi: {answer}

Dat 1 tieu de THAT NGAN GON (toi da 6 tu, tieng Viet co dau) cho cuoc tro chuyen nay, tom tat
dung chu de dang hoi. CHI tra ve DUNG tieu de — khong dau ngoac kep, khong dau cham cuoi cau,
khong giai thich gi them, khong xuong dong."""
    try:
        result = await gemini.generate(prompt)
    except Exception:
        return _FALLBACK_TITLE
    title = result.text.strip().strip('"').strip("'").strip()
    if not title:
        return _FALLBACK_TITLE
    # De phong Gemini van tra ve nhieu dong du da can dan — chi lay dong dau, cat gon do dai.
    return title.splitlines()[0].strip()[:255]
