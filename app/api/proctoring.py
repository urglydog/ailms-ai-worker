"""UC-ANTICHEAT (25/09/2026) — AI Anti-Cheat, Composite Behavioral Risk Engine cho bài thi
proctored (`Quiz.isProctored`). BE gọi đồng bộ 2 endpoint dưới đây, đúng khuôn
`QuizService.explainWrongAnswer` gọi `/api/v1/tutor/ask` (không phải Celery/Redis — đây là
lệnh gọi cần phản hồi nhanh, không phải pipeline media dài).

- `POST /analyze-frame`: xác minh 1 khung hình webcam bằng Gemini Vision thật (đếm người +
  đánh giá ĐỊNH TÍNH hướng nhìn/ánh mắt — Gemini là mô hình đa phương thức, nhìn ảnh đánh giá
  như 1 giám thị con người, KHÔNG phải đo toạ độ iris chính xác bằng hình học; face-api.js
  68-điểm dùng ở FE không có landmark iris nên không làm được phép đo đó).
- `POST /assess-risk`: cuối phiên thi (lúc nộp bài), BE gửi tổng hợp SỐ ĐẾM từng loại vi phạm
  đã ghi nhận trong phiên đó, Gemini suy luận 1 lần duy nhất ra `risk_level`/`explanation` —
  đây là phần LLM reasoning trên tín hiệu hành vi đa dạng, khác hẳn đếm-vi-phạm-đơn-thuần.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.providers import gemini
from app.providers.base import ProviderInvalidResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/proctoring", tags=["proctoring"])


def _extract_json(text: str) -> dict:
    """Gemini được yêu cầu trả JSON thuần nhưng có thể bọc trong ```json fences — cùng cách xử
    lý với `services/translation.py::_extract_json`."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderInvalidResponse(f"Gemini tra ve JSON khong hop le: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# POST /analyze-frame — Gemini Vision, 1 khung hình webcam
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeFrameReq(BaseModel):
    image_base64: str = Field(min_length=1)
    mime_type: str = "image/jpeg"


class AnalyzeFrameRes(BaseModel):
    person_count: int
    gaze_direction: str  # "screen" | "away" | "down" | "unknown"
    reasoning: str


# BUG THẬT (26/09/2026): bản cũ gộp chung "faces/people" trong 1 câu hỏi — khi thí sinh quay
# hẳn đầu sang 1 bên (mặt không thấy rõ) nhưng người vẫn ngồi đó, Gemini trả lời theo nghĩa
# "face" nên person_count=0, sụp về NO_FACE thay vì đáng lẽ phải là GAZE_AWAY (BE đã đúng logic
# person_count==0 → NO_FACE, còn lại xét gaze_direction — lỗi nằm ở chỗ prompt khiến model
# không phân biệt được 2 khái niệm). Tách hẳn 2 câu hỏi: đếm SỰ HIỆN DIỆN của người (đầu/vai/
# thân trong khung hình, không yêu cầu thấy rõ mặt) độc lập với hướng nhìn; "unknown" chỉ dùng
# khi thật sự không xác định được (quá tối, camera bị che/mờ) — quay mặt đi vẫn xác định được
# hướng là "away", không phải "unknown".
_FRAME_PROMPT = """You are an exam proctoring assistant analyzing ONE webcam frame from a
student taking an online exam. Look carefully at the image and answer TWO INDEPENDENT questions:

1. How many distinct people are PRESENT in the frame — counting anyone whose head, shoulders or
   body is visible, even if their face is NOT visible (e.g. turned away, back of head only). Do
   NOT require a visible face to count a person as present.
2. Independently, where is the (primary) person's gaze/head direction pointed, based on whatever
   is visible? Choose exactly one:
   - "screen": facing/looking toward their own screen/camera, normal exam posture
   - "away": head or body turned clearly to the side or away from the screen (including when the
     face itself is no longer visible because they turned away — this is still "away", NOT
     "unknown")
   - "down": looking down (possibly at a phone or notes on the desk)
   - "unknown": ONLY when direction genuinely cannot be judged at all — frame too dark, camera
     blocked/obstructed, or no person present in the frame

Respond with ONLY a JSON object, no markdown fences, no extra text:
{"person_count": <int>, "gaze_direction": "<screen|away|down|unknown>", "reasoning": "<1 short sentence in Vietnamese>"}
"""


@router.post("/analyze-frame", response_model=AnalyzeFrameRes, status_code=status.HTTP_200_OK)
async def analyze_frame(request: AnalyzeFrameReq) -> AnalyzeFrameRes:
    # BUG THẬT (26/09/2026): payload ảnh không hợp lệ trước đây đi thẳng tới Gemini, bị Google từ
    # chối với 400 — nhưng do gemini.py trước đó coi MỌI 400 là "key có vấn đề" nên đã khoá oan 1
    # key khoẻ mạnh 1 tiếng (xem fix ở gemini.py::_execute_request). Chặn payload sai NGAY TỪ ĐÂY
    # vừa tránh tốn 1 lượt gọi API vô ích, vừa không phụ thuộc vào việc gemini.py phân loại đúng.
    try:
        base64.b64decode(request.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"image_base64 khong hop le: {exc}")

    contents = [
        {
            "role": "user",
            "parts": [
                {"text": _FRAME_PROMPT},
                {"inlineData": {"mimeType": request.mime_type, "data": request.image_base64}},
            ],
        }
    ]
    try:
        result = await gemini.generate_conversation(contents)
        if isinstance(result, gemini.FunctionCall):
            raise ProviderInvalidResponse("Gemini tra ve FunctionCall thay vi text cho phan tich khung hinh")
        data = _extract_json(result.text)
        return AnalyzeFrameRes(
            person_count=int(data.get("person_count", 0)),
            gaze_direction=str(data.get("gaze_direction", "unknown")),
            reasoning=str(data.get("reasoning", "")),
        )
    except Exception as e:
        log.warning("analyze_frame that bai: %s", e)
        raise HTTPException(status_code=500, detail=f"Proctoring analyze-frame failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /assess-risk — Composite Risk Scoring, 1 lần/attempt lúc nộp bài
# ─────────────────────────────────────────────────────────────────────────────

class AssessRiskReq(BaseModel):
    violation_counts: dict[str, int] = Field(default_factory=dict)
    duration_sec: int = 0
    question_count: int = 0


class AssessRiskRes(BaseModel):
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH"
    explanation: str


_RISK_SYSTEM_INSTRUCTION = """You are an exam integrity analyst. You receive a structured
summary of behavioral signals collected during ONE proctored exam session (tab switches,
window blur, fullscreen exits, face/gaze anomalies, detected voice audio, idle time, copy-paste
attempts, devtools usage). You must reason holistically about how suspicious this session looks
as a WHOLE, not just count violations — a single tab-switch is normal, but many correlated
signals (e.g. repeated gaze-away + voice detected + idle-too-long) suggest a much higher risk of
cheating (e.g. using a second device via remote control) than the same total count spread across
harmless one-off events.

IMPORTANT: you cannot directly detect remote-desktop tools — only reason from the signals given.
Respond with ONLY a JSON object, no markdown fences:
{"risk_level": "<LOW|MEDIUM|HIGH>", "explanation": "<2-4 câu tiếng Việt giải thích lý do, nêu cụ thể tín hiệu nào đáng chú ý nhất>"}
"""


@router.post("/assess-risk", response_model=AssessRiskRes, status_code=status.HTTP_200_OK)
async def assess_risk(request: AssessRiskReq) -> AssessRiskRes:
    prompt = (
        f"Violation counts by type: {json.dumps(request.violation_counts, ensure_ascii=False)}\n"
        f"Exam duration: {request.duration_sec} seconds\n"
        f"Question count: {request.question_count}\n\n"
        "Assess the cheating risk level for this session."
    )
    try:
        result = await gemini.generate(prompt, system_instruction=_RISK_SYSTEM_INSTRUCTION)
        data = _extract_json(result.text)
        risk_level = str(data.get("risk_level", "LOW")).upper()
        if risk_level not in ("LOW", "MEDIUM", "HIGH"):
            risk_level = "LOW"
        return AssessRiskRes(risk_level=risk_level, explanation=str(data.get("explanation", "")))
    except Exception as e:
        log.warning("assess_risk that bai, fallback LOW: %s", e)
        # Fail-open (khớp docblock be/QuizService.assessRisk) — không có nhận định AI thì
        # coi như LOW thay vì chặn hiển thị kết quả bài thi.
        return AssessRiskRes(risk_level="LOW", explanation="Không thể phân tích rủi ro tự động lúc này.")
