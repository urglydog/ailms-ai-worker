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
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.http import backend_client
from app.providers import gemini, supabase_vector
from app.providers.base import ProviderInvalidResponse

_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):([0-5]?\d)\]")


@dataclass(frozen=True)
class TutorAnswer:
    answer: str
    cited_timestamps: list[int]
    token_used: int


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


def _build_system_instruction(lesson_title: str, course_title: str, course_description: str, language: str | None = None) -> str:
    topic = course_description or course_title
    
    lang_rule = ""
    if language:
        lang_rule = f"\nCRITICAL INSTRUCTION: You MUST write your ENTIRE response in the language corresponding to the language code '{language}'. DO NOT use Vietnamese or English unless it is the requested language."

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
   cung tu choi kieu nay) — chi dat lai 1-2 cau hoi goi mo de hoc vien tu suy luan. BAT
   BUOC trich it nhat 1 moc thoi gian dung dinh dang [MM:SS] tu ngu canh duoc cung cap,
   KHONG duoc bia moc khong co trong ngu canh.
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


@dataclass(frozen=True)
class Attachment:
    """1 tep hoc vien gui kem cau hoi — `data_base64` la noi dung tep DA ma hoa base64,
    gui thang cho Gemini duoi dang `inlineData` (BR-TUTOR-03 mo rong: cung 1 luot goi,
    khong can lenh phan loai rieng — xem `_build_system_instruction` quy tac 3)."""

    mime_type: str
    data_base64: str


async def answer(
    lesson_id: int, question: str, history: list[dict] | None = None, attachments: list[Attachment] | None = None,
    language: str | None = None,
) -> TutorAnswer:
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
    )


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
