"""UC19 — dịch bằng Gemini (BR-DUB-02).

`doc/DEVELOPMENT_PLAN.md` mục 1 mô tả pipeline dịch "3 bước": direct translation ->
context-aware adaptation -> timing constraint alignment. Ở đây gộp bước 2 và 3 thành
MỘT lời gọi Gemini (thay vì 3 lời gọi riêng biệt) — "3 bước" là 3 giai đoạn xử lý về
mặt nghiệp vụ, không bắt buộc là 3 request API. Gộp lại còn 2 lời gọi/chunk (thay vì
2 × số câu) để không vượt `GEMINI_RATE_LIMIT_RPM` của Free Tier (mục 3
`doc/SETUP_GIAIDOAN5.md`).
"""

from __future__ import annotations

import json
import re

from langcodes import Language

from app.models import Segment
from app.providers import gemini
from app.providers.base import ProviderInvalidResponse


def _natural_language_name(locale_code: str) -> str:
    """Chuyển mã locale (vi-VN, en-US, hay mã trần "en" tu Groq...) sang ten ngon ngu tu
    nhien (Vietnamese, English...) de dua vao prompt Gemini — khop cach VideoLingo dung
    `target_language` dang ten tu nhien (core/st_utils/sidebar_setting.py: "Input any
    language in natural language, as long as llm can understand"). Dung `langcodes` (du
    lieu ISO 639 chuan) thay vi tu liet ke bang ten ngon ngu, de khong vi pham BR-DUB-07
    (khong hardcode danh sach ngon ngu o bat ky dau) va tu hoat dong voi BAT KY ngon ngu
    nao `voice_mappings` co the them sau nay.
    """
    try:
        return Language.get(locale_code).language_name() or locale_code
    except Exception:
        return locale_code


def _extract_json(text: str) -> dict:
    """Gemini được yêu cầu trả JSON thuần nhưng có thể bọc trong ```json fences."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderInvalidResponse(f"Gemini tra ve JSON khong hop le: {exc}") from exc


def _build_direct_prompt(numbered: dict[str, str], source_lang: str, target_lang: str) -> str:
    source_name = _natural_language_name(source_lang)
    target_name = _natural_language_name(target_lang)
    lines_json = json.dumps(numbered, ensure_ascii=False, indent=2)
    return f"""## Role
Ban la bien dich vien chuyen nghiep, dich {source_name} sang {target_name} cho video bai giang.

## Task
Dich TUNG dong duoi day tu {source_name} sang {target_name}, dich SAT NGHIA, khong bo sot
noi dung, khong them binh luan rieng. Giu dung so luong dong dau vao.

## INPUT
{lines_json}

## Output CHI JSON, khong them chu nao khac, dung dinh dang:
{{"1": "ban dich dong 1", "2": "ban dich dong 2", ...}}
""".strip()


def _build_adapt_prompt(direct: dict[str, str], durations_sec: dict[str, float], target_lang: str) -> str:
    target_name = _natural_language_name(target_lang)
    combined = {
        key: {"text": direct.get(key, ""), "budget_sec": round(durations_sec.get(key, 0.0), 1)}
        for key in direct
    }
    combined_json = json.dumps(combined, ensure_ascii=False, indent=2)
    return f"""## Role
Ban la bien tap vien phu de/loi thoai cho video giao duc bang {target_name}.

## Task
Voi moi dong duoi day, viet lai ban dich cho tu nhien va de nghe khi doc thanh loi
(dung cho Text-to-Speech), GIU NGUYEN y nghia giao duc cot loi. "budget_sec" la thoi
luong noi cua cau goc de tham khao — co gang dien dat GON de vua thoi luong do NHUNG
TUYET DOI khong duoc hy sinh do ro rang hay lam mat y nghia chi de chay theo thoi
luong.

## INPUT
{combined_json}

## Output CHI JSON, khong them chu nao khac, dung dinh dang:
{{"1": "ban dich da bien tap dong 1", ...}}
""".strip()


async def translate_batch(segments: list[Segment], source_lang: str, target_lang: str) -> list[str]:
    """Dịch toàn bộ câu trong MỘT chunk 10 phút (BR-CHUNK-02) theo batch — 2 lời gọi
    Gemini cho cả chunk, không phải 2 lời gọi cho mỗi câu.
    """
    if not segments:
        return []

    numbered = {str(i + 1): seg.text for i, seg in enumerate(segments)}
    direct_result = await gemini.generate(_build_direct_prompt(numbered, source_lang, target_lang))
    direct_map = _extract_json(direct_result.text)

    durations = {str(i + 1): seg.duration for i, seg in enumerate(segments)}
    adapt_result = await gemini.generate(_build_adapt_prompt(direct_map, durations, target_lang))
    adapt_map = _extract_json(adapt_result.text)

    return [
        (adapt_map.get(str(i + 1)) or direct_map.get(str(i + 1)) or "").strip()
        for i in range(len(segments))
    ]


async def resummarize(text: str, target_lang: str) -> str:
    """BR-DUB-03 nhánh R > 1.3 — rút gọn bản dịch, giữ nguyên ý nghĩa cốt lõi.

    Gọi cho TỪNG câu riêng lẻ (không batch) vì đây là nhánh hiếm gặp, chỉ kích hoạt
    khi bản dịch quá dài so với thời lượng gốc — không đáng để phức tạp hoá bằng batch.
    """
    target_name = _natural_language_name(target_lang)
    prompt = f"""## Role
Ban la bien tap vien rut gon loi thoai cho video giao duc bang {target_name}.

## Task
Cau sau qua dai so voi thoi luong noi cho phep. Rut gon lai NGAN HON, bo bot tu de/
lap lai khong can thiet, GIU NGUYEN thong tin va y nghia giao duc cot loi.

## INPUT
{text}

## Output CHI van ban da rut gon, KHONG giai thich, KHONG dua vao dau ngoac kep.
""".strip()
    result = await gemini.generate(prompt)
    return result.text.strip().strip('"')
