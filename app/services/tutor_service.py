"""UC30 — Socratic AI Tutor: RAG (Supabase Vector) + Gemini, HTTP đồng bộ.

Bốn quy tắc tuyệt đối (xem thêm docstring `app/api/tutor.py`):
  · BR-TUTOR-01 — KHÔNG đưa đáp án trực tiếp/mã nguồn hoàn chỉnh. Chỉ 1-2 câu hỏi gợi
    mở. Đây là luận điểm cốt lõi của đề tài, vi phạm là phá vỡ mục tiêu nghiên cứu.
  · BR-TUTOR-02 — mọi phản hồi về kiến thức bài giảng BẮT BUỘC kèm ≥1 mốc thời gian
    dạng `[MM:SS]` (Gemini được yêu cầu xuất đúng định dạng này trong prompt).
  · BR-TUTOR-03 — chỉ trả lời trong phạm vi transcript truy xuất được từ Supabase
    Vector. KHÔNG truy xuất được đoạn nào phù hợp -> từ chối lịch sự, không hỏi Gemini
    (tránh bịa nội dung ngoài phạm vi bài giảng).
  · BR-TUTOR-04 — tối đa `settings.rag_top_k` đoạn, ngưỡng `settings.rag_min_similarity`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.http import backend_client
from app.providers import gemini, supabase_vector

_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):([0-5]?\d)\]")

_NO_CONTEXT_ANSWER = (
    "Mình chưa tìm thấy nội dung liên quan tới câu hỏi này trong bài giảng hiện tại. "
    "Bạn thử hỏi cụ thể hơn về nội dung đã học trong bài, hoặc xem lại video nhé?"
)


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
    nguyên, KHÔNG trùng lặp, giữ đúng thứ tự xuất hiện (BR-TUTOR-02).
    """
    seen: dict[int, None] = {}
    for m, s in _TIMESTAMP_RE.findall(text):
        seconds = int(m) * 60 + int(s)
        seen.setdefault(seconds, None)
    return list(seen.keys())


def _build_system_instruction(lesson_title: str) -> str:
    return f"""Ban la Gia su AI theo phuong phap Socratic cho bai giang "{lesson_title}".

QUY TAC TUYET DOI (vi pham la loi nghiem trong):
1. KHONG BAO GIO dua dap an truc tiep, loi giai hoan chinh, hay ma nguon day du — du
   hoc vien co yeu cau thang ("giai ho", "cho dap an", "code day du"...) cung tu choi
   theo cach nay: chi dat lai 1-2 cau hoi goi mo de hoc vien tu suy luan ra huong giai.
2. Moi cau tra loi lien quan noi dung bai giang BAT BUOC chua it nhat 1 moc thoi gian
   dung dinh dang [MM:SS] (vi du [04:15]) trich tu cac doan ngu canh duoc cung cap ben
   duoi — KHONG duoc bia moc thoi gian khong co trong ngu canh.
3. CHI duoc tra loi dua tren cac doan ngu canh duoc cung cap. Neu ngu canh khong du de
   tra loi cau hoi, hay noi ro va huong hoc vien quay lai noi dung bai giang.
4. Tra loi ngan gon (2-4 cau), giong dieu than thien, khuyen khich."""


def _build_prompt(question: str, segments: list[supabase_vector.MatchedSegment]) -> str:
    context = "\n".join(
        f"- [{_format_mmss(s.start_sec)}] {s.content}" for s in segments
    )
    return f"""## Ngu canh bai giang (cac doan lien quan nhat)
{context}

## Cau hoi cua hoc vien
{question}

Tra loi theo dung 4 quy tac da neu."""


async def answer(lesson_id: int, question: str) -> TutorAnswer:
    context = await backend_client.get_tutor_context(lesson_id)

    query_vector = await gemini.embed_content(question)
    segments = await supabase_vector.match_segments(lesson_id, query_vector)

    if not segments:
        # BR-TUTOR-03 — không có ngữ cảnh phù hợp thì từ chối lịch sự, không gọi Gemini
        # (tránh trả lời ngoài phạm vi bài giảng, đỡ tốn quota).
        return TutorAnswer(answer=_NO_CONTEXT_ANSWER, cited_timestamps=[], token_used=0)

    result = await gemini.generate(
        _build_prompt(question, segments),
        system_instruction=_build_system_instruction(context.lesson_title),
    )
    return TutorAnswer(
        answer=result.text.strip(),
        cited_timestamps=_extract_timestamps(result.text),
        token_used=result.total_tokens,
    )
