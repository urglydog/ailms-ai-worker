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
- keyword is a search term.
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
                        "description": "Search keyword for title or description."
                    }
                }
            }
        }
    ]
}


@router.post("/chat", response_model=DiscoveryChatResponse, status_code=status.HTTP_200_OK)
async def chat(request: DiscoveryChatRequest) -> DiscoveryChatResponse:
    """Handler mong: chi parse input, goi service, tra response."""
    try:
        res = await gemini.generate_with_tools(
            prompt=request.message,
            tools=[search_tool],
            system_instruction=SYSTEM_INSTRUCTION
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
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
                    
                reply_text = f"Tôi đã tìm thấy {len(courses)} khóa học phù hợp với yêu cầu của bạn." if courses else "Rất tiếc, tôi không tìm thấy khóa học nào phù hợp với yêu cầu của bạn."
                return DiscoveryChatResponse(reply=reply_text, courses=courses)
    else:
        # LLM returned text (e.g. refused to answer or small talk)
        return DiscoveryChatResponse(reply=res.text, courses=[])
