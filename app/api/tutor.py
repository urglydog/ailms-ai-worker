"""UC30 — Socratic AI Tutor (HTTP dong bo).

Bon quy tac tuyet doi khong duoc lam sai:
  · BR-TUTOR-01 — KHONG dua dap an truc tiep hay ma nguon hoan chinh.
    Chi 1-2 cau hoi goi mo de hoc vien tu suy luan. Day la luan diem cot loi
    cua de tai, vi pham la pha vo muc tieu nghien cuu.
  · BR-TUTOR-02 — moi phan hoi ve kien thuc bai giang BAT BUOC kem it nhat
    mot moc thoi gian nhap duoc.
  · BR-TUTOR-03 (mo rong) — uu tien tra loi trong pham vi transcript truy xuat tu
    Supabase Vector; KHONG tim thay doan nao du lien quan (duoi nguong
    settings.rag_min_similarity) thi fallback Google Search Grounding, co guard-rail
    chu de trong system prompt (xem app/services/tutor_service.py::answer).
  · BR-TUTOR-04 — toi da 30 tin nhan/hoc vien/ngay, RAG lay toi da 5 doan.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services import tutor_service

router = APIRouter(prefix="/api/v1/tutor", tags=["tutor"])

#: UC30 mở rộng — trần số tệp/lượt hỏi, lớp phòng vệ cuối (be/ đã chặn trước ở tầng nhận
#: upload) — không tin tưởng mù quáng dữ liệu từ service khác dù là nội bộ.
_MAX_ATTACHMENTS_PER_TURN = 3


class HistoryTurn(BaseModel):
    sender: str  # "USER" hoac "AI" — khop ChatMessage.sender ben be/
    content: str


class AttachmentIn(BaseModel):
    mime_type: str
    #: Noi dung tep DA ma hoa base64 — be/ tu upload len B2 rieng, day chi la ban sao gui
    #: cho Gemini phan tich, KHONG phai nguon luu tru.
    data_base64: str = Field(min_length=1)


class TutorAskRequest(BaseModel):
    lesson_id: int
    question: str = Field(min_length=1, max_length=2000)
    session_id: int | None = None
    #: UC30 mở rộng — vài lượt gần nhất của phiên chat (cũ -> mới, KHÔNG gồm câu hỏi hiện
    #: tại), để Gemini nhớ được ngữ cảnh câu hỏi nối tiếp kiểu "câu hỏi trên là gì?".
    history: list[HistoryTurn] = Field(default_factory=list)
    #: UC30 mở rộng — tệp học viên đính kèm cùng câu hỏi (ảnh/tài liệu/mã nguồn).
    attachments: list[AttachmentIn] = Field(default_factory=list)
    language: str | None = None


class TutorAskResponse(BaseModel):
    answer: str
    #: Mang giay, vi du [255, 612]. BAT BUOC co it nhat 1 phan tu khi cau tra loi
    #: lien quan kien thuc bai giang (BR-TUTOR-02).
    cited_timestamps: list[int]
    token_used: int


@router.post("/ask", response_model=TutorAskResponse, status_code=status.HTTP_200_OK)
async def ask(request: TutorAskRequest) -> TutorAskResponse:
    """Handler mong: chi parse input, goi service, tra response.

    `session_id` nhan tu request nhung khong dung o day — AI Worker khong ghi MySQL,
    BE moi la noi so huu ChatSession/ChatMessage (goi dong bo endpoint nay roi tu luu
    lai ca cau hoi lan cau tra loi).
    """
    if len(request.attachments) > _MAX_ATTACHMENTS_PER_TURN:
        raise HTTPException(status_code=400, detail=f"Toi da {_MAX_ATTACHMENTS_PER_TURN} tep moi luot hoi")

    result = await tutor_service.answer(
        request.lesson_id,
        request.question,
        history=[t.model_dump() for t in request.history],
        attachments=[tutor_service.Attachment(mime_type=a.mime_type, data_base64=a.data_base64) for a in request.attachments],
        language=request.language,
    )
    return TutorAskResponse(
        answer=result.answer,
        cited_timestamps=result.cited_timestamps,
        token_used=result.token_used,
    )


class TutorTitleRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=4000)


class TutorTitleResponse(BaseModel):
    title: str


@router.post("/title", response_model=TutorTitleResponse, status_code=status.HTTP_200_OK)
async def title(request: TutorTitleRequest) -> TutorTitleResponse:
    """UC30 mở rộng — be/ gọi ĐÚNG 1 LẦN ngay sau lượt hỏi đầu tiên của 1 phiên chat mới, để
    tự đặt tên cuộc trò chuyện (giống ChatGPT/Gemini) thay vì luôn rút gọn câu hỏi đầu."""
    generated = await tutor_service.generate_title(request.question, request.answer)
    return TutorTitleResponse(title=generated)
