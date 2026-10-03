import json
import logging
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.providers import gemini

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/study-plan", tags=["study-plan"])

# BUG THẬT (03/10/2026) — "hôm nay" ở đây trước dùng datetime.now() KHÔNG timezone (giờ máy
# chủ AI worker, có thể là UTC) trong khi BE StudentStudyPlanService dùng Asia/Ho_Chi_Minh
# (reschedulePlan) hoặc JVM default zone (generatePlan) — 3 nơi tính "hôm nay" khác nhau cho
# cùng 1 tính năng. Cố định về Asia/Ho_Chi_Minh ở cả 3 nơi để nhất quán (xem StudentStudyPlanService.VN_ZONE).
VN_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")

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
        - Hôm nay là: {datetime.now(VN_ZONE).strftime('%Y-%m-%d')}
        - Ngày mục tiêu kết thúc: {req.targetDate}
        - Số giờ học mỗi tuần: {req.hoursPerWeek} giờ
        
        DANH SÁCH BÀI GIẢNG CẦN HỌC:
        {lessons_text}
        
        YÊU CẦU:
        1. BẮT ĐẦU NGAY LẬP TỨC: Lịch học phải bắt đầu từ HÔM NAY (hoặc ngày mai). Tuyệt đối không được dồn toàn bộ bài học vào những ngày cuối cùng sát ngày mục tiêu. Hãy phân bổ đều ra các ngày.
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

        # BUG THẬT (03/10/2026) — StudyPlanResponse đã khai báo từ trước nhưng KHÔNG hề được
        # dùng để validate: JSON cú pháp hợp lệ nhưng thiếu field/sai kiểu (Gemini lệch schema)
        # vẫn lọt qua đây, chỉ vỡ (lỗi 500 chung) rất xa về sau ở BE lúc deserialize Jackson.
        # response_schema chỉ RÀNG BUỘC Gemini cố gắng tuân thủ, không đảm bảo tuyệt đối.
        try:
            StudyPlanResponse.model_validate(plan_data)
        except ValidationError as ve:
            logger.error(f"Gemini tra JSON sai schema StudyPlanResponse: {ve}")
            raise HTTPException(status_code=502, detail="AI trả về dữ liệu lộ trình không đúng cấu trúc, vui lòng thử lại.")

        return plan_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating study plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

