"""Tùy chọn trong form tạo học liệu (số lượng, độ khó, mức chi tiết mindmap) → chỉ dẫn trong prompt (BR-MAT-05).

Trước 21/11/2026 các giá trị này được lưu và gửi sang worker nhưng KHÔNG được đưa vào prompt nên chọn "Nhiều/Khó" không có tác dụng (số câu/thẻ do model tự quyết, dao động 5–21).
Số lượng theo nhãn trên form: Ít ≈ 10, Vừa ≈ 20, Nhiều ≈ 30 (câu hỏi hoặc thẻ) cho CẢ KHÓA; phạm vi hẹp hơn tính theo tỷ lệ số bài, sàn 5 câu / 10 thẻ.
Giá trị trống/lạ → không thêm chỉ dẫn nào (giữ hành vi cũ), nên học liệu tạo từ API cũ hoặc thiếu tham số vẫn chạy như trước.
"""

from __future__ import annotations

_BASE = {"FEWER": 10, "STANDARD": 20, "MORE": 30}
QUIZ_FLOOR = 5
CARD_FLOOR = 10


def scope_ratio(lessons_in_scope: int, course_lessons: int | None) -> float:
    """Tỷ lệ số bài trong phạm vi so với cả khóa (tối đa 1). Thiếu thông tin → 1 (không thu nhỏ)."""
    if not course_lessons or course_lessons <= 0 or lessons_in_scope <= 0:
        return 1.0
    return min(1.0, lessons_in_scope / course_lessons)


def target_count(kind: str, quantity: str | None, ratio: float = 1.0) -> int | None:
    """Số câu hỏi/thẻ mục tiêu; None nếu không có mức số lượng hợp lệ. kind: "QUIZ" | "FLASHCARD"."""
    base = _BASE.get((quantity or "").upper())
    if base is None:
        return None
    floor = QUIZ_FLOOR if kind == "QUIZ" else CARD_FLOOR
    ratio = max(0.0, min(1.0, ratio))
    return min(base, max(floor, round(base * ratio)))


_DIFFICULTY = {
    "EASY": (
        "MUC DO KHO: DE (ghi nho / dinh nghia). Hoi truc tiep ve thuat ngu, dinh nghia, su kien neu ro trong noi dung; "
        "cac phuong an sai de nhan ra."
    ),
    "MEDIUM": (
        "MUC DO KHO: TRUNG BINH (hieu / ap dung). Hoi ve y nghia, nguyen nhan, vi du ap dung; cac phuong an sai nghe hop ly."
    ),
    "HARD": (
        "MUC DO KHO: KHO (phan tich / so sanh / danh gia). Hoi so sanh, phan tich nguyen nhan - he qua, tinh huong van dung; "
        "cac phuong an sai phai hop ly de gay nham lan, KHONG hoi dinh nghia tra tu."
    ),
}


def quiz_clauses(quantity: str | None, difficulty: str | None, ratio: float = 1.0) -> list[str]:
    """Các dòng yêu cầu thêm cho prompt Quiz (không kèm số thứ tự)."""
    out: list[str] = []
    n = target_count("QUIZ", quantity, ratio)
    if n:
        out.append(
            f"SO LUONG: Sinh khoang {n} cau hoi (lech toi da 20%). Neu noi dung khong du de co ngan ay cau hoi KHAC NHAU thi sinh it hon, "
            "KHONG lap lai y, KHONG bia them thong tin ngoai noi dung."
        )
    d = _DIFFICULTY.get((difficulty or "").upper())
    if d:
        out.append(d)
    return out


def flashcard_clauses(quantity: str | None, ratio: float = 1.0) -> list[str]:
    n = target_count("FLASHCARD", quantity, ratio)
    if not n:
        return []
    return [
        f"SO LUONG: Sinh khoang {n} the (lech toi da 20%), moi the chi MOT khai niem. Neu noi dung khong du khai niem khac nhau thi sinh it hon, "
        "KHONG lap lai, KHONG bia them thong tin ngoai noi dung."
    ]


_MINDMAP_DEPTH = {
    "FEWER": "Do sau toi da 3 cap, chi giu cac nhanh chinh (khoang 12-18 node).",
    "STANDARD": "Do sau toi da 4 cap (khoang 25-35 node).",
    "MORE": "Do sau toi da 5 cap, chi tiet, chia nhieu nhanh nho (khoang 40-60 node).",
}


def mindmap_depth_line(quantity: str | None) -> str | None:
    """Dòng thay cho "Do sau toi da 4-5 cap" của prompt mặc định; None nếu không có mức hợp lệ."""
    return _MINDMAP_DEPTH.get((quantity or "").upper())


def numbered(start: int, clauses: list[str]) -> str:
    """Ghép các dòng yêu cầu thêm thành văn bản có đánh số, bắt đầu từ `start`; rỗng nếu không có dòng nào."""
    return "".join(f"\n    {start + i}. {c}" for i, c in enumerate(clauses))
