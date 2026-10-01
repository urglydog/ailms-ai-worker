import json
import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.providers import gemini

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/study-plan", tags=["study-plan"])

class LessonInfo(BaseModel):
    id: int
    title: str
    durationSec: int
    chapterTitle: str

class AiWorkerStudyPlanReq(BaseModel):
    targetDate: str
    hoursPerWeek: int
    remainingLessons: List[LessonInfo]

class StudyLesson(BaseModel):
    lesson_id: int
    title: str
    duration_minutes: int

class StudyDay(BaseModel):
    date: str
    lessons: List[StudyLesson]
    objective: str

class StudyPlanResponse(BaseModel):
    plan_data: List[StudyDay]

@router.post("/generate")
async def generate_study_plan(req: AiWorkerStudyPlanReq):
    try:
        lessons_text = "\n".join([f"- Bài {l.id}: {l.title} (Thời lượng: {l.durationSec // 60} phút) - Chương: {l.chapterTitle}" for l in req.remainingLessons])
        
        prompt = f"""
        Bạn là một chuyên gia giáo dục AI. Nhiệm vụ của bạn là lập lịch học cá nhân hóa cho học viên.
        
        THÔNG TIN HỌC VIÊN:
        - Hôm nay là: {datetime.now().strftime('%Y-%m-%d')}
        - Ngày mục tiêu kết thúc: {req.targetDate}
        - Số giờ học mỗi tuần: {req.hoursPerWeek} giờ
        
        DANH SÁCH BÀI GIẢNG CẦN HỌC:
        {lessons_text}
        
        YÊU CẦU:
        1. Phân bổ đều các bài giảng này vào các ngày từ hôm nay (hoặc ngày mai) đến {req.targetDate}.
        2. Đảm bảo tổng thời gian học mỗi tuần không vượt quá {req.hoursPerWeek} giờ.
        3. Đối với mỗi ngày học, xác định danh sách bài cần học và một mục tiêu học tập (objective) ngắn gọn.
        4. Trả về đúng định dạng JSON Schema yêu cầu. Tuyệt đối không thêm giải thích hay thẻ markdown.
        5. TUYỆT ĐỐI KHÔNG xếp các bài giảng thuộc 2 Chương (Chapter) khác nhau vào cùng 1 ngày học. Mỗi ngày chỉ học các bài của CÙNG 1 chương. Nếu đã hết bài của chương đó mà vẫn còn thời gian của ngày, hãy để học viên nghỉ ngơi, KHÔNG lấy bài của chương tiếp theo sang học ghép vào cùng ngày!
        """
        
        schema = {
            "type": "object",
            "properties": {
                "plan_data": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "objective": {"type": "string"},
                            "lessons": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "lesson_id": {"type": "integer"},
                                        "title": {"type": "string"},
                                        "duration_minutes": {"type": "integer"}
                                    },
                                    "required": ["lesson_id", "title", "duration_minutes"]
                                }
                            }
                        },
                        "required": ["date", "objective", "lessons"]
                    }
                }
            },
            "required": ["plan_data"]
        }
        
        res = await gemini.generate_conversation(
            [{"role": "user", "parts": [{"text": prompt}]}],
            response_mime_type="application/json",
            response_schema=schema
        )
        
        if isinstance(res, gemini.FunctionCall):
            raise ValueError("Expected text but got FunctionCall from Gemini")
            
        plan_data = json.loads(res.text)
        return plan_data
        
    except Exception as e:
        logger.error(f"Error generating study plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

