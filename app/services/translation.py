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

from app import usage as usage_mod
from app.config import settings
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


def _thinking() -> str | None:
    return settings.dubbing_thinking_level or None


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


def _build_dub_prompt(segments: list[Segment], max_chars: list[int | None], source_lang: str, target_lang: str) -> str:
    source_name = _natural_language_name(source_lang)
    target_name = _natural_language_name(target_lang)
    lines = {}
    for i, seg in enumerate(segments):
        item: dict = {"text": seg.text, "budget_sec": round(seg.duration, 1)}
        if max_chars[i]:
            item["max_chars"] = max_chars[i]
        lines[str(i + 1)] = item
    return f"""## Role
Ban la bien dich vien kiem bien tap loi thoai long tieng video bai giang, dich {source_name} sang {target_name}.

## Task
Voi MOI dong duoi day, dich sang {target_name} va viet luon thanh loi noi TU NHIEN, de nghe khi
doc bang Text-to-Speech:
- Dung nghia, khong bo sot y, giu thuat ngu chuyen mon; khong them binh luan.
- "budget_sec" la thoi luong noi cua cau goc: dien dat GON de doc vua thoi luong do.
- Neu co "max_chars": ban dich KHONG duoc vuot so ky tu nay (bo tu dem/lap, KHONG bo y chinh).
- Giu dung so dong, khong gop hay tach dong, khong bo dong nao.

## INPUT
{json.dumps(lines, ensure_ascii=False, indent=2)}

## Output CHI JSON, khong them chu nao khac, dung dinh dang:
{{"1": "ban dich dong 1", "2": "ban dich dong 2", ...}}
""".strip()


@usage_mod.tagged("DUBBING_TRANSLATE")
async def translate_batch(
    segments: list[Segment], source_lang: str, target_lang: str, max_chars: list[int | None] | None = None,
) -> list[str]:
    """Dịch toàn bộ câu trong MỘT chunk 10 phút (BR-CHUNK-02) — 1 lời gọi Gemini cho cả chunk.

    15/11/2026: gộp "dịch sát nghĩa" + "biên tập cho tự nhiên/vừa thời lượng" (trước là 2 lời gọi,
    bản dịch sát nghĩa chỉ để làm dự phòng) thành 1 lời gọi; "3 bước" của pipeline dịch là 3 giai
    đoạn nghiệp vụ, không bắt buộc là 3 request. `max_chars` (tuỳ chọn, ước theo tốc độ đọc đo được
    của giọng) giúp bản dịch vừa khung NGAY từ đầu -> ít câu phải rút gọn và đọc lại TTS.
    """
    if not segments:
        return []
    limits = list(max_chars) if max_chars and len(max_chars) == len(segments) else [None] * len(segments)

    result = await gemini.generate(_build_dub_prompt(segments, limits, source_lang, target_lang), thinking_level=_thinking())
    mapped = _extract_json(result.text)
    out = [_as_text(mapped.get(str(i + 1))) for i in range(len(segments))]
    # Gemini (nhất là khi suy nghĩ ở mức thấp) đôi khi bỏ sót vài dòng cuối -> câu rỗng, Azure trả
    # file 0 byte làm hỏng cả chunk (job 30, 15/11/2026). Dịch lại riêng các dòng thiếu trong 1 lời
    # gọi; vẫn thiếu thì giữ câu gốc để chunk không bao giờ có câu rỗng.
    missing = [i for i, text in enumerate(out) if not text]
    if missing:
        retry_map = _extract_json((await gemini.generate(
            _build_direct_prompt({str(k + 1): segments[i].text for k, i in enumerate(missing)}, source_lang, target_lang),
            thinking_level=_thinking(),
        )).text)
        for k, i in enumerate(missing):
            out[i] = _as_text(retry_map.get(str(k + 1))) or segments[i].text.strip()
    return out


def _as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


@usage_mod.tagged("DUBBING_TRANSLATE")
async def resummarize_batch(items: list[tuple[str, int]], target_lang: str) -> list[str]:
    """Rút gọn NHIỀU câu trong MỘT lời gọi Gemini (hiệu năng dubbing, S4).

    `items` = [(bản dịch, số ký tự tối đa)]. Trả về danh sách cùng độ dài; câu nào LLM không trả
    về (hoặc trả rỗng) thì giữ nguyên bản cũ — caller vẫn còn nhánh tăng tốc tối đa làm lưới an toàn.
    Trước đây gọi `resummarize` cho TỪNG câu: ~32% số câu bị rút gọn -> hàng trăm lời gọi mỗi bài.
    """
    if not items:
        return []
    target_name = _natural_language_name(target_lang)
    numbered = {str(i + 1): {"text": text, "max_chars": max_chars} for i, (text, max_chars) in enumerate(items)}
    prompt = f"""## Role
Ban la bien tap vien rut gon loi thoai cho video giao duc bang {target_name}.

## Task
Moi dong duoi day qua dai so voi thoi luong noi cho phep. Rut gon tung dong sao cho KHONG vuot
"max_chars" ky tu, bo bot tu dem/lap lai, GIU NGUYEN thong tin va y nghia giao duc cot loi.
Khong gop hay tach dong.

## INPUT
{json.dumps(numbered, ensure_ascii=False, indent=2)}

## Output CHI JSON, khong them chu nao khac, dung dinh dang:
{{"1": "dong 1 da rut gon", "2": "dong 2 da rut gon", ...}}
""".strip()
    result = await gemini.generate(prompt, thinking_level=_thinking())
    mapped = _extract_json(result.text)
    out: list[str] = []
    for i, (text, _max) in enumerate(items):
        value = mapped.get(str(i + 1))
        out.append(value.strip().strip('"') if isinstance(value, str) and value.strip() else text)
    return out


@usage_mod.tagged("DUBBING_TRANSLATE")
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
    result = await gemini.generate(prompt, thinking_level=_thinking())
    return result.text.strip().strip('"')
