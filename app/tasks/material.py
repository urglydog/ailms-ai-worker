"""UC25 — Creator Agent sinh hoc lieu (Celery).

BR-MAT-03: luon bat dong bo, du kien 30-90 giay voi pham vi ca khoa hoc.
Backend tra 202 Accepted + generationId, KHONG cho trong HTTP request.

BR-MAT-06 — validate dau ra LLM truoc khi luu:
  · Quiz/Flashcards phai la JSON dung schema
  · Mindmap phai bien dich duoc bang Mermaid.js
  · Sai thi goi lai LLM toi da 2 lan voi chi dan sua loi dinh dang
  · Van sai -> GenStatus.FAILED + nut "Thu tao lai", va KHONG duoc lam gian doan
    pipeline long tieng chinh

BR-QUIZ-01/02: cau hoi chi gom noi dung + dung 4 phuong an + dap an dung.
KHONG sinh explanation, KHONG sinh moc thoi gian.
"""

from __future__ import annotations

from app.celery_app import celery_app


@celery_app.task(bind=True, name="app.tasks.material.generate_material")
def generate_material(self, generation_id: int) -> dict:
    """Sinh mot bo hoc lieu theo tham so da luu trong MaterialGeneration."""
    raise NotImplementedError("Se duoc hien thuc o Giai doan 7. Doc skill lms-multi-agent truoc.")
