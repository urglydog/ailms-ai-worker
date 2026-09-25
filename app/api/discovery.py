"""UC49 — Course Discovery Agent (HTTP dong bo, STATELESS).

BR-DISCOVERY-01: KHONG luu lich su hoi thoai — chat chi ton tai trong phien
trinh duyet. Vi vay agent nay KHONG dung ChatSession/ChatMessage.
Han ngach: Guest 15 tin/IP/gio, Student 30 tin/ngay.

BR-DISCOVERY-02: chi tra loi cau hoi ve tim kiem/tu van khoa hoc tren nen tang.
Tu choi lich su voi chu de ngoai pham vi.

Ky thuat: Gemini Function Calling dich cau hoi tu nhien thanh
search_courses(category, level, price_type, keyword) roi truy van qua backend.

UC49 nang cap (25/09/2026) — Hybrid semantic search: BE van la nguoi duy nhat quyet
dinh course nao duoc phep hien (status/visibility), buoc loc cung category/level/
priceType o duoi giu nguyen; sau do rerank tap ung vien do bang cosine similarity
(pgvector, tai dung ha tang cua Socratic Tutor — xem `providers/supabase_vector.py`)
de cau hoi KHONG trung tu khoa voi ten/mo ta khoa hoc van ra dung ket qua. Fail-open:
loi embedding/Supabase khong duoc lam hong ket qua filter-only von da hoat dong.
"""

import logging

import httpx
from fastapi import APIRouter, status, HTTPException
from pydantic import BaseModel, Field

from app.providers import gemini, supabase_vector
from app.http import backend_client
from app.config import settings

log = logging.getLogger(__name__)

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
- categorySlug: ONLY use one of the exact slug values listed in the tool schema's enum for this field
  (mapped from the platform's real categories). If the user's intent does not clearly match any of
  those exact categories, OMIT this parameter entirely — do NOT invent or guess a slug.
- level can be BEGINNER, INTERMEDIATE, ADVANCED.
- priceType can be FREE, PAID.
- keyword: MUST be a concise search term derived from the user's intent. For example, if the user wants to "build a website", use keywords like "web", "html", or "css". If they want to learn "english", use "tiếng anh" or "english". DO NOT use long phrases as keywords.
"""


async def _fetch_category_slugs() -> list[dict]:
    """UC49 nâng cấp (25/09/2026) — BUG THẬT phát hiện lúc test: system prompt cũ đưa VÍ DỤ
    categorySlug sai ("it, language, business", không khớp slug thật trong DB kiểu
    "ngoai-ngu-chuyen-nganh"), khiến Gemini đoán bừa → BE lọc cứng theo slug KHÔNG TỒN TẠI →
    luôn trả về 0 khóa học, che khuất luôn cả bước rerank semantic mới thêm (không có ứng viên
    nào để rerank). Lấy đúng danh sách category THẬT từ BE, ép Gemini chỉ được chọn trong enum
    này hoặc bỏ qua field — không còn tự bịa slug nữa.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.internal_be_url}/api/v1/categories")
            if resp.status_code != 200:
                return []
            return resp.json()
    except Exception as exc:
        log.warning("Khong lay duoc danh sach category, bo qua enum categorySlug: %s", exc)
        return []


def _build_search_tool(categories: list[dict]) -> dict:
    category_slug_property: dict = {
        "type": "STRING",
        "description": "The exact category slug matching user intent. Pick ONLY from the enum list below, or omit if none fit.",
    }
    if categories:
        category_slug_property["enum"] = [c["slug"] for c in categories]
        mapping = ", ".join(f"{c['name']} -> {c['slug']}" for c in categories)
        category_slug_property["description"] += f" Categories: {mapping}."

    return {
        "functionDeclarations": [
            {
                "name": "search_courses",
                "description": "Search for courses on the platform based on user preferences.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "categorySlug": category_slug_property,
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
        # Bước 1: Trích xuất intent — enum categorySlug lấy từ danh mục THẬT, tránh Gemini
        # bịa slug không tồn tại (xem docblock `_fetch_category_slugs`).
        categories = await _fetch_category_slugs()
        res = await gemini.generate_with_tools(
            prompt=request.message,
            tools=[_build_search_tool(categories)],
            system_instruction=SYSTEM_INSTRUCTION
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Request Failed: {e}")
        
    if isinstance(res, gemini.FunctionCall):
        if res.name == "search_courses":
            args = res.arguments
            # UC49 nang cap: KHONG gui "keyword" cho BE nua — BE chi con LIKE tren title,
            # gioi han ket qua o dung cau chu trung khop. Giu filter cung
            # (category/level/priceType) nhu cu, lay pool ung vien rong hon de rerank
            # bang similarity ben duoi thay vi loc chu nghia den.
            params = {"size": settings.discovery_candidate_pool_size}
            if "categorySlug" in args:
                params["categorySlug"] = args["categorySlug"]
            if "level" in args:
                params["level"] = args["level"]
            if "priceType" in args:
                params["priceType"] = args["priceType"]

            # Backend call — dùng `backend_client` dùng chung (đã có sẵn header
            # `X-Internal-Token` đúng chuẩn dự án, xem docblock `instructor_ai.py::_fetch_backend`
            # về bug thật do tự mở client với header `Authorization: Bearer` sai). API
            # `/api/v1/courses` public nên trước đây header sai vẫn "chạy được" — vô hại NHƯNG
            # chỉ vì tình cờ, sẽ vỡ y hệt instructor_ai.py nếu endpoint này từng chuyển vào
            # `/api/internal/**`.
            be_res = await backend_client.get_client().get("/api/v1/courses", params=params)
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

            # UC49 nâng cấp — rerank tập ứng viên (đã lọc cứng ở BE) bằng cosine
            # similarity để câu hỏi không trùng từ khóa với title/description vẫn ra
            # đúng khóa liên quan. Fail-open: lỗi ở đây giữ nguyên `courses` gốc
            # (filter-only), KHÔNG bao giờ làm kết quả tệ hơn hành vi cũ.
            #
            # BUG THẬT (25/09/2026, phát hiện lúc test câu hỏi hoàn toàn không liên quan
            # như "nấu ăn"): khi KHÔNG có filter cứng nào (category/level/priceType đều
            # rỗng), `courses` ở trên là TOÀN BỘ catalog (BE không lọc gì cả), không phải
            # 1 tập đã được BE "vetted" theo đúng ý người dùng. Nếu không course nào đạt
            # ngưỡng similarity mà vẫn fail-open giữ nguyên `courses`, kết quả là hiện HẾT
            # catalog cho 1 câu hỏi hoàn toàn lạc đề — mâu thuẫn với câu trả lời text (nói
            # "không có khóa nào phù hợp" nhưng card vẫn hiện đủ). Chỉ fail-open giữ
            # `courses` gốc khi có ÍT NHẤT 1 filter cứng thật sự áp dụng (BE đã tự vetted
            # theo đúng category/level/price người dùng nêu); không có filter nào cả +
            # không similarity nào đạt ngưỡng → trả rỗng mới trung thực.
            has_hard_filter = any(k in args for k in ("categorySlug", "level", "priceType"))
            if courses:
                try:
                    query_vector = await gemini.embed_content(request.message)
                    matches = await supabase_vector.match_courses_by_ids(
                        course_ids=[c.id for c in courses],
                        query_embedding=query_vector,
                    )
                    similarity_by_id = {m.course_id: m.similarity for m in matches}
                    if similarity_by_id:
                        courses = sorted(
                            (c for c in courses if c.id in similarity_by_id),
                            key=lambda c: similarity_by_id[c.id],
                            reverse=True,
                        )
                    elif not has_hard_filter:
                        courses = []
                    # Có filter cứng nhưng không similarity nào đạt ngưỡng (vd course chưa
                    # kịp embed) — giữ nguyên danh sách filter-only gốc, không trả về rỗng.
                except Exception as exc:
                    log.warning("Rerank semantic that bai, dung ket qua filter goc: %s", exc)

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
