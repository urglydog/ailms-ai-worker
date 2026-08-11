"""UC-INSTRUCTOR-AI — Instructor AI Assistant (HTTP đồng bộ, stateless).

Khác với Discovery Chat (UC49) phục vụ Student/Guest tìm khóa học,
Instructor AI Assistant phục vụ nhu cầu quản lý và tối ưu hóa khóa học.

Tools hỗ trợ:
  · get_my_course_stats    — xem số liệu học viên, doanh thu của khóa mình
  · analyze_reviews        — phân tích đánh giá học viên, tóm tắt điểm yếu/mạnh
  · suggest_course_content — gợi ý cải thiện mô tả, tiêu đề, cấu trúc khóa học

Kiến trúc: FE → Backend (JWT + INSTRUCTOR role check) → đây (AI Worker nội bộ)
KHÔNG expose ra ngoài — gọi từ InstructorAiController.java qua mạng Docker.
"""

from __future__ import annotations

import logging
import httpx

from fastapi import APIRouter, status, HTTPException
from pydantic import BaseModel, Field

from app.providers import gemini
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/instructor", tags=["instructor-ai"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class InstructorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    caller_role: str = "INSTRUCTOR"          # Bắt buộc phải là INSTRUCTOR
    instructor_email: str = ""               # Dùng để fetch data từ backend


class InstructorChatResponse(BaseModel):
    reply: str
    data: dict | None = None                 # Dữ liệu trả về từ function call (nếu có)


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — Instructor context, hoàn toàn khác Discovery
# ─────────────────────────────────────────────────────────────────────────────

INSTRUCTOR_SYSTEM_PROMPT = """You are an AI Teaching Assistant for instructors on an e-learning platform.
Your role is to help instructors:
1. Understand their course performance (enrollments, revenue, reviews)
2. Analyze student feedback to identify strengths and weaknesses
3. Suggest improvements for course content, titles, and descriptions
4. Provide teaching best practices

You have access to tools to fetch real data from the platform.
Always be constructive, data-driven, and professional.
Respond in Vietnamese unless the instructor writes in English.

IMPORTANT: You are NOT a course discovery agent. Do not help instructors "find courses to learn from".
Your purpose is to help them BUILD and IMPROVE their own courses.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Function Calling Tools — KHÁC với Discovery Agent
# ─────────────────────────────────────────────────────────────────────────────

instructor_tools = [
    {
        "functionDeclarations": [
            {
                "name": "get_my_course_stats",
                "description": "Get statistics for instructor's own courses: enrollment count, revenue, ratings.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "course_id": {
                            "type": "INTEGER",
                            "description": "Specific course ID to get stats for. If omitted, return stats for all courses."
                        },
                        "period": {
                            "type": "STRING",
                            "description": "Time period: 'this_month', 'last_month', 'this_year', 'all_time'. Default: 'all_time'."
                        }
                    }
                }
            },
            {
                "name": "analyze_reviews",
                "description": "Analyze student reviews for a course. Returns sentiment summary, common complaints, and strengths.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "course_id": {
                            "type": "INTEGER",
                            "description": "Course ID to analyze reviews for."
                        }
                    },
                    "required": ["course_id"]
                }
            },
            {
                "name": "suggest_course_content",
                "description": "Suggest improvements for course title, description, or structure based on best practices.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "course_title": {
                            "type": "STRING",
                            "description": "Current course title to improve."
                        },
                        "course_description": {
                            "type": "STRING",
                            "description": "Current course description to improve."
                        },
                        "target_audience": {
                            "type": "STRING",
                            "description": "Who is this course for? e.g., 'beginners in Python', 'marketing professionals'"
                        }
                    }
                }
            }
        ]
    }
]


# ─────────────────────────────────────────────────────────────────────────────
# Helper: fetch dữ liệu từ Backend
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_backend(path: str) -> dict:
    """Gọi nội bộ về Backend để lấy dữ liệu thật."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{settings.internal_be_url}{path}",
                headers={"Authorization": f"Bearer {settings.internal_api_token}"}
            )
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"Backend returned {resp.status_code}"}
        except Exception as e:
            log.error(f"Backend fetch failed for {path}: {e}")
            return {"error": str(e)}


async def _handle_function_call(
    fn_name: str,
    args: dict,
    instructor_email: str,
) -> dict:
    """Thực thi function call từ Gemini và trả về dữ liệu thực."""
    if fn_name == "get_my_course_stats":
        data = await _fetch_backend(
            f"/api/v1/dashboard/instructor?email={instructor_email}"
        )
        return {
            "function": "get_my_course_stats",
            "data": data,
            "period": args.get("period", "all_time"),
        }

    elif fn_name == "analyze_reviews":
        course_id = args.get("course_id")
        data = await _fetch_backend(
            f"/api/v1/courses/{course_id}/reviews?size=100&includeHidden=false"
        )
        content = data.get("content", [])
        if not content:
            return {"function": "analyze_reviews", "message": "Khóa học này chưa có đánh giá nào."}

        # Tính thống kê cơ bản
        ratings = [r.get("rating", 0) for r in content]
        avg = sum(ratings) / len(ratings) if ratings else 0
        low_rated = [r for r in content if r.get("rating", 5) <= 2]
        high_rated = [r for r in content if r.get("rating", 0) >= 4]

        return {
            "function": "analyze_reviews",
            "total_reviews": len(content),
            "average_rating": round(avg, 2),
            "positive_count": len(high_rated),
            "negative_count": len(low_rated),
            "sample_negative": [r.get("comment") for r in low_rated[:5] if r.get("comment")],
            "sample_positive": [r.get("comment") for r in high_rated[:5] if r.get("comment")],
        }

    elif fn_name == "suggest_course_content":
        # Không cần gọi backend — LLM tự sinh gợi ý
        return {
            "function": "suggest_course_content",
            "input": args,
            "note": "LLM will generate suggestions based on context"
        }

    return {"error": f"Unknown function: {fn_name}"}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=InstructorChatResponse, status_code=status.HTTP_200_OK)
async def instructor_chat(request: InstructorChatRequest) -> InstructorChatResponse:
    """Instructor AI Assistant — backend đã xác thực role trước khi gọi vào đây."""
    # Guard: chỉ chấp nhận request từ backend proxy (caller_role phải là INSTRUCTOR)
    if request.caller_role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="This endpoint is for INSTRUCTOR only.")

    try:
        res = await gemini.generate_with_tools(
            prompt=request.message,
            tools=instructor_tools,
            system_instruction=INSTRUCTOR_SYSTEM_PROMPT,
        )
    except Exception as e:
        log.error(f"Gemini call failed in instructor AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if isinstance(res, gemini.FunctionCall):
        fn_data = await _handle_function_call(
            res.name, res.arguments, request.instructor_email
        )

        # Gọi Gemini lần 2 với dữ liệu thực để sinh câu trả lời tự nhiên
        summary_prompt = (
            f"Dữ liệu từ hệ thống:\n{fn_data}\n\n"
            f"Câu hỏi của giảng viên: {request.message}\n\n"
            "Hãy phân tích dữ liệu trên và trả lời câu hỏi của giảng viên "
            "một cách ngắn gọn, dễ hiểu và actionable."
        )
        try:
            summary_res = await gemini.generate(summary_prompt, system_instruction=INSTRUCTOR_SYSTEM_PROMPT)
            return InstructorChatResponse(reply=summary_res.text, data=fn_data)
        except Exception:
            return InstructorChatResponse(
                reply="Đã lấy được dữ liệu nhưng không thể tóm tắt. Xem chi tiết trong phần data.",
                data=fn_data
            )
    else:
        return InstructorChatResponse(reply=res.text)
