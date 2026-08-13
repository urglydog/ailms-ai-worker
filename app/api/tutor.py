"""UC30 — Socratic AI Tutor (HTTP dong bo).

Bon quy tac tuyet doi khong duoc lam sai:
  · BR-TUTOR-01 — KHONG dua dap an truc tiep hay ma nguon hoan chinh.
    Chi 1-2 cau hoi goi mo de hoc vien tu suy luan. Day la luan diem cot loi
    cua de tai, vi pham la pha vo muc tieu nghien cuu.
  · BR-TUTOR-02 — moi phan hoi ve kien thuc bai giang BAT BUOC kem it nhat
    mot moc thoi gian nhap duoc.
  · BR-TUTOR-03 — chi tra loi trong pham vi transcript truy xuat tu Supabase
    Vector; ngoai pham vi thi tu choi lich su.
  · BR-TUTOR-04 — toi da 30 tin nhan/hoc vien/ngay, RAG lay toi da 5 doan.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services import tutor_service

router = APIRouter(prefix="/api/v1/tutor", tags=["tutor"])


class TutorAskRequest(BaseModel):
    lesson_id: int
    question: str = Field(min_length=1, max_length=2000)
    session_id: int | None = None


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
    result = await tutor_service.answer(request.lesson_id, request.question)
    return TutorAskResponse(
        answer=result.answer,
        cited_timestamps=result.cited_timestamps,
        token_used=result.token_used,
    )
