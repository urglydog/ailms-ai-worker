"""UC49 — Course Discovery Agent (HTTP dong bo, STATELESS).

BR-DISCOVERY-01: KHONG luu lich su hoi thoai — chat chi ton tai trong phien
trinh duyet. Vi vay agent nay KHONG dung ChatSession/ChatMessage.
Han ngach: Guest 15 tin/IP/gio, Student 30 tin/ngay.

BR-DISCOVERY-02: chi tra loi cau hoi ve tim kiem/tu van khoa hoc tren nen tang.
Tu choi lich su voi chu de ngoai pham vi.

Ky thuat: Gemini Function Calling dich cau hoi tu nhien thanh
search_courses(category, level, price_type, keyword) roi truy van qua backend.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])


class DiscoveryChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class CourseCardDto(BaseModel):
    """The khoa hoc hien trong khung chat."""

    id: int
    title: str
    slug: str
    instructor_name: str
    price_label: str
    is_free: bool
    rating: float
    level_label: str


class DiscoveryChatResponse(BaseModel):
    reply: str
    courses: list[CourseCardDto]


@router.post("/chat", response_model=DiscoveryChatResponse, status_code=status.HTTP_200_OK)
async def chat(request: DiscoveryChatRequest) -> DiscoveryChatResponse:
    """Handler mong: chi parse input, goi service, tra response."""
    raise NotImplementedError("Se duoc hien thuc o Giai doan 8 (UC49).")
