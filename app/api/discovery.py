"""UC49 — Course Discovery Agent (HTTP dong bo, STATELESS).

BR-DISCOVERY-01: KHONG luu lich su hoi thoai — chat chi ton tai trong phien
trinh duyet. Vi vay agent nay KHONG dung ChatSession/ChatMessage.
Han ngach: Guest 15 tin/IP/gio, Student 30 tin/ngay.

BR-DISCOVERY-02: chi tra loi cau hoi ve tim kiem/tu van khoa hoc tren nen tang.
Tu choi lich su voi chu de ngoai pham vi.

Ky thuat: Gemini Function Calling dich cau hoi tu nhien thanh
search_courses(category, level, price_type, keyword) roi truy van qua backend.
"""

import httpx
from fastapi import APIRouter, status, HTTPException
from pydantic import BaseModel, Field

from app.providers import gemini
from app.config import settings

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


SYSTEM_INSTRUCTION = """You are a Course Discovery Agent for an e-learning platform.
Your job is to help users find courses on the platform.
You should ONLY answer questions related to searching or recommending courses on this platform.
If the user asks something completely unrelated, politely decline and steer the conversation back to finding courses.

Use the `search_courses` function to search for courses based on user queries.
You must extract the parameters (categorySlug, level, priceType, keyword) from the user's message.
- level can be BEGINNER, INTERMEDIATE, ADVANCED.
- priceType can be FREE, PAID.
- keyword: MUST be a concise search term derived from the user's intent. For example, if the user wants to "build a website", use keywords like "web", "html", or "css". If they want to learn "english", use "tiếng anh" or "english". DO NOT use long phrases as keywords.
"""

search_tool = {
    "functionDeclarations": [
        {
            "name": "search_courses",
            "description": "Search for courses on the platform based on user preferences.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "categorySlug": {
                        "type": "STRING",
                        "description": "The slug of the category (e.g., it, language, business)."
                    },
                    "level": {
                        "type": "STRING",
                        "description": "Course difficulty. Allowed values: BEGINNER, INTERMEDIATE, ADVANCED."
                    },
                    "priceType": {
                        "type": "STRING",
                        "description": "Price type. Allowed values: FREE, PAID."
                    },
                    "keyword": {
                        "type": "STRING",
                        "description": "Search keyword for title or description. Extract this carefully from the user's implicit or explicit intent."
                    }
                }
            }
        }
    ]
}


@router.post("/chat", response_model=DiscoveryChatResponse, status_code=status.HTTP_200_OK)
async def chat(request: DiscoveryChatRequest) -> DiscoveryChatResponse:
    """Handler 2 bước: Bước 1 gọi AI trích xuất intent, Bước 2 lấy data thật gọi AI lần 2 để trả lời."""
    try:
        # Bước 1: Trích xuất intent
        res = await gemini.generate_with_tools(
            prompt=request.message,
            tools=[search_tool],
            system_instruction=SYSTEM_INSTRUCTION
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Request Failed: {e}")
        
    if isinstance(res, gemini.FunctionCall):
        if res.name == "search_courses":
            args = res.arguments
            params = {}
            if "categorySlug" in args:
                params["categorySlug"] = args["categorySlug"]
            if "level" in args:
                params["level"] = args["level"]
            if "priceType" in args:
                params["priceType"] = args["priceType"]
            if "keyword" in args:
                params["keyword"] = args["keyword"]
                
            # Backend call
            async with httpx.AsyncClient() as client:
                be_res = await client.get(
                    f"{settings.internal_be_url}/api/v1/courses",
                    params=params,
                    # API này public nên không cần token, nhưng ta vẫn truyền
                    headers={"Authorization": f"Bearer {settings.internal_api_token}"}
                )
                if be_res.status_code != 200:
                    raise HTTPException(status_code=500, detail="Backend error")
                
                data = be_res.json()
                content = data.get("content", [])
                
                courses = []
                for c in content:
                    price_val = c.get("price")
                    if c.get("isFree"):
                        price_label = "Miễn phí"
                    else:
                        price_label = f"{int(price_val):,} VND" if price_val else "Liên hệ"
                        
                    courses.append(CourseCardDto(
                        id=c["id"],
                        title=c["title"],
                        slug=c["slug"],
                        instructor_name=c.get("instructorName", ""),
                        price_label=price_label,
                        is_free=c.get("isFree", False),
                        rating=float(c.get("avgRating", 0)),
                        level_label=c.get("level", "ALL")
                    ))
                
                # Bước 2: Sinh câu trả lời dựa trên kết quả thật
                # Tóm tắt tối đa 5 khóa học để tránh quá tải payload (chỉ cần title và price để AI biết)
                summary_data = [
                    {"title": c.title, "price": c.price_label, "level": c.level_label}
                    for c in courses[:5]
                ]
                
                prompt2 = f"""Người dùng đã hỏi: "{request.message}"
Dưới đây là kết quả tìm kiếm khóa học từ cơ sở dữ liệu dựa trên ý định của họ:
{summary_data}
(Tổng số khóa học tìm thấy: {len(courses)})

Hãy đóng vai trợ lý tư vấn khóa học, viết một câu trả lời tự nhiên cho người dùng:
- Nếu danh sách trống, hãy nhẹ nhàng xin lỗi và nói rằng hiện chưa có khóa học nào khớp chính xác, và đưa ra lời khuyên.
- Nếu có khóa học, hãy giới thiệu sơ qua một cách thân thiện (không cần liệt kê chi tiết vì chúng đã được hiển thị trên giao diện, chỉ cần nói chung chung).
Tuyệt đối KHÔNG tự bịa ra khóa học không có trong danh sách trên."""
                
                try:
                    final_res = await gemini.generate(
                        prompt=prompt2,
                        system_instruction="Bạn là trợ lý tư vấn khóa học thân thiện, chuyên nghiệp."
                    )
                    reply_text = final_res.text
                except Exception as e:
                    # Fallback nếu AI lần 2 lỗi
                    reply_text = f"Tôi đã tìm thấy {len(courses)} khóa học phù hợp với yêu cầu của bạn." if courses else "Rất tiếc, tôi không tìm thấy khóa học nào phù hợp với yêu cầu của bạn."
                    
                return DiscoveryChatResponse(reply=reply_text, courses=courses)
    else:
        # LLM returned text (e.g. refused to answer or small talk)
        return DiscoveryChatResponse(reply=res.text, courses=[])
