"""Lớp 2b chống Prompt Injection/DoW (UpComming_Plan.md, phân tích 25/09/2026) — quét heuristic
pattern nghi vấn TRƯỚC khi build prompt gửi Gemini cho AI Discovery / Instructor AI Assistant.

Chỉ GHI LOG (qua `backend_client.report_prompt_security_flag`) để Admin xem lại, KHÔNG chặn câu
trả lời — tránh false positive làm gián đoạn người dùng thật. Tham khảo danh sách pattern ở
`be/DacTa_ChongPromptInjection_TutorAgent.md` §5.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_instructions", re.compile(r"(bỏ qua (mọi|tất cả|hướng dẫn)|ignore (previous|the above|all))", re.IGNORECASE)),
    ("claims_admin", re.compile(r"tôi là (admin|quản trị|dev|nhân viên)", re.IGNORECASE)),
    ("reveal_system_prompt", re.compile(r"system\s*prompt", re.IGNORECASE)),
    ("destructive_request", re.compile(r"(xóa hết|xoá hết|drop table|delete from)", re.IGNORECASE)),
    ("role_override", re.compile(r"(act as|pretend you are|bạn hãy đóng vai)", re.IGNORECASE)),
    ("dan_jailbreak", re.compile(r"\bDAN\b")),
    ("pasted_official_content", re.compile(r"(nội dung (chính thức|bài học)|official (lesson )?content)", re.IGNORECASE)),
]


def scan(message: str) -> str | None:
    """Trả về tên pattern KHỚP ĐẦU TIÊN, hoặc `None` nếu không có gì đáng chú ý."""
    for name, pattern in _PATTERNS:
        if pattern.search(message):
            return name
    return None
