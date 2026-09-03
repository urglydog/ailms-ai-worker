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

import asyncio
import logging
import json

from app import redis_client
from app.celery_app import celery_app
from app.http import backend_client
from app.providers import gemini, supabase_vector

log = logging.getLogger(__name__)

async def _run_and_cleanup(generation_id: int) -> dict:
    try:
        # Fetch context
        context = await backend_client.get_material_context(generation_id)
        if not context.transcripts:
            await backend_client.finish_material_generation(generation_id, outcome="FAILED", error_message="Khong co transcript de sinh hoc lieu")
            return {"status": "FAILED", "reason": "No transcripts"}
            
        full_text = " ".join([t["text"] for t in context.transcripts])
        
        if context.material_type == "MINDMAP":
            mermaid_code = await _generate_mindmap(full_text, context.language)
            if mermaid_code:
                await backend_client.finish_material_generation(generation_id, outcome="COMPLETED", mermaid_code=mermaid_code)
                return {"status": "COMPLETED"}
            else:
                await backend_client.finish_material_generation(generation_id, outcome="FAILED", error_message="Khong the sinh Mermaid hop le sau 2 lan thu")
                return {"status": "FAILED", "reason": "Mermaid invalid"}
        elif context.material_type == "FLASHCARD":
            flashcards = await _generate_flashcards(full_text, context.language)
            if flashcards:
                await backend_client.finish_material_generation(generation_id, outcome="COMPLETED", flashcards=flashcards)
                return {"status": "COMPLETED"}
            else:
                await backend_client.finish_material_generation(generation_id, outcome="FAILED", error_message="Khong the sinh Flashcard hop le sau 2 lan thu")
                return {"status": "FAILED", "reason": "Flashcards invalid"}
        elif context.material_type == "QUIZ":
            quizzes = await _generate_quizzes(full_text, context.language)
            if quizzes:
                await backend_client.finish_material_generation(generation_id, outcome="COMPLETED", quizzes=quizzes)
                return {"status": "COMPLETED"}
            else:
                await backend_client.finish_material_generation(generation_id, outcome="FAILED", error_message="Khong the sinh Quiz hop le sau 2 lan thu")
                return {"status": "FAILED", "reason": "Quizzes invalid"}
        else:
            await backend_client.finish_material_generation(generation_id, outcome="FAILED", error_message=f"Chua ho tro {context.material_type}")
            return {"status": "FAILED"}
    except Exception as e:
        log.exception("Loi sinh hoc lieu")
        await backend_client.finish_material_generation(generation_id, outcome="FAILED", error_message=str(e))
        return {"status": "FAILED", "error": str(e)}
    finally:
        await asyncio.gather(
            backend_client.aclose(),
            gemini.aclose(),
            supabase_vector.aclose(),
            redis_client.aclose(),
            return_exceptions=True,
        )

async def _generate_mindmap(text: str, language: str) -> str | None:
    prompt = f"""
    Ban la mot chuyen gia giao duc. Hay tao mot so do tu duy (Mindmap) bang Mermaid.js cho noi dung bai hoc sau day.
    Yeu cau:
    1. Chi tra ve ma nguon Mermaid, khong giai thich gi them.
    2. Su dung cu phap flowchart cua Mermaid (bat dau bang 'flowchart TD').
    3. Do sau toi da 4-5 cap.
    4. Noi dung phai ngan gon, suc tich.
    5. QUAN TRONG: TOAN BO NOI DUNG TRONG MINDMAP PHAI DUOC DICH SANG NGON NGU CO MA CODE: '{language}' (Vi du: 'zh-CN' la Tieng Trung, 'en-US' la Tieng Anh, 'vi-VN' la Tieng Viet).
    6. QUAN TRONG: KHONG DUOC phep su dung markdown syntax trong text cua node:
       - KHONG dung dau gach dau dong (- hay *)
       - KHONG bat dau text bang "so." (vi du "1. abc") vi Mermaid se hieu nham la ordered list
       - Neu can danh so, dung "(so)" thay vi "so." (vi du: "(1) Dieu kien" thay vi "1. Dieu kien")
       - KHONG dung the HTML
    7. QUAN TRONG: LUON LUON bao quanh text cua node bang dau ngoac kep de tranh loi cu phap. Vi du: NodeID["(1) Noi dung"] thay vi NodeID[(1) Noi dung]
    
    Noi dung:
    {text[:500000]}
    """
    
    for attempt in range(2):
        response = await gemini.generate(prompt)
        # Extract markdown block if any
        code = response.text.strip()
        if code.startswith("```mermaid"):
            code = code[10:]
            if code.endswith("```"):
                code = code[:-3]
        elif code.startswith("```"):
            code = code[3:]
            if code.endswith("```"):
                code = code[:-3]
        code = code.strip()
        
        # Simple validation
        if code.startswith("flowchart") or code.startswith("graph"):
            return code
            
        log.warning(f"Mermaid code khong hop le lan {attempt + 1}, dang thu lai. Code: {code}")
        prompt += "\nLuu y: Ban da tra ve sai cu phap trong lan truoc. Hay chac chan dung dung cu phap flowchart TD cua Mermaid va khong dung markdown list trong text!"
        
    return None

async def _generate_flashcards(text: str, language: str) -> list[dict] | None:
    prompt = f"""
    Ban la mot chuyen gia giao duc. Hay tao mot bo Flashcards (The ghi nho) cho noi dung bai hoc sau day.
    Yeu cau:
    1. Chi tra ve JSON Array, khong giai thich gi them.
    2. Moi the co "front_text" (cau hoi/thuat ngu) va "back_text" (giai thich/dinh nghia).
    3. Dinh dang JSON chinh xac: [{{"front_text": "...", "back_text": "..."}}, ...]
    4. QUAN TRONG: TOAN BO NOI DUNG FLASHCARDS PHAI DUOC DICH SANG NGON NGU CO MA CODE: '{language}' (Vi du: 'zh-CN' la Tieng Trung, 'en-US' la Tieng Anh, 'vi-VN' la Tieng Viet).
    
    Noi dung:
    {text[:500000]}
    """
    
    for attempt in range(2):
        response = await gemini.generate(prompt)
        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
        elif content.startswith("```"):
            content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
        content = content.strip()
        
        try:
            data = json.loads(content)
            if isinstance(data, list) and len(data) > 0 and "front_text" in data[0] and "back_text" in data[0]:
                return data
        except json.JSONDecodeError:
            pass
            
        log.warning(f"Flashcard JSON khong hop le lan {attempt + 1}, dang thu lai. Output: {content}")
        prompt += "\nLuu y: Ban da tra ve sai dinh dang JSON trong lan truoc. Hay chac chan tra ve JSON array hop le!"
        
    return None

async def _generate_quizzes(text: str, language: str) -> list[dict] | None:
    prompt = f"""
    Ban la mot chuyen gia giao duc. Hay tao mot bo cau hoi trac nghiem (Quiz) cho noi dung bai hoc sau day.
    Yeu cau:
    1. Chi tra ve JSON Array, khong giai thich gi them.
    2. Moi cau hoi co "content" (noi dung cau hoi), "options" (mang DUNG 4 phuong an), va "correct_answer" (chuoi nguyen van 1 trong 4 phuong an).
    3. KHONG sinh giai thich (explanation), KHONG sinh moc thoi gian (timestamp).
    4. Dinh dang JSON chinh xac: [{{"content": "...", "options": ["A", "B", "C", "D"], "correct_answer": "..."}}, ...]
    5. QUAN TRONG: TOAN BO NOI DUNG QUIZ PHAI DUOC DICH SANG NGON NGU CO MA CODE: '{language}' (Vi du: 'zh-CN' la Tieng Trung, 'en-US' la Tieng Anh, 'vi-VN' la Tieng Viet).
    
    Noi dung:
    {text[:500000]}
    """
    
    for attempt in range(2):
        response = await gemini.generate(prompt)
        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
        elif content.startswith("```"):
            content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
        content = content.strip()
        
        try:
            data = json.loads(content)
            if isinstance(data, list) and len(data) > 0 and "content" in data[0] and "options" in data[0] and len(data[0]["options"]) == 4 and "correct_answer" in data[0]:
                return data
        except json.JSONDecodeError:
            pass
            
        log.warning(f"Quiz JSON khong hop le lan {attempt + 1}, dang thu lai. Output: {content}")
        prompt += "\nLuu y: Ban da tra ve sai dinh dang JSON trong lan truoc. Hay chac chan tra ve JSON array hop le va dung 4 options!"
        
    return None

@celery_app.task(bind=True, name="app.tasks.material.generate_material")
def generate_material(self, generation_id: int) -> dict:
    """Sinh mot bo hoc lieu theo tham so da luu trong MaterialGeneration."""
    log.info("Bat dau sinh hoc lieu generation_id=%s", generation_id)
    return asyncio.run(_run_and_cleanup(generation_id))

