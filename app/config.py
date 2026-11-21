"""Cấu hình AI Worker — đọc toàn bộ từ biến môi trường.

BR-DUB-02 cấm hardcode tên model LLM, nên `gemini_model` bắt buộc đến từ env.
Xem `project/ai-worker/.env.example` để biết danh sách biến (Giai đoạn 5 tách
riêng khỏi `project/be/.env.example` — mỗi service tự có file env của mình).
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Hạ tầng ──────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # AI Worker KHÔNG kết nối MySQL trực tiếp (xem ai-agent/context/architecture.md).
    # Mọi thay đổi dữ liệu phải gọi callback về backend qua URL này.
    internal_be_url: str = "http://localhost:8080"
    internal_api_token: str = "dev-internal-token"

    # ── STT ──────────────────────────────────────────────────
    # Mặc định Groq (§5.1.1: không phụ thuộc GPU).
    # whisperx_local chỉ dùng khi đo đối chứng cho Chương 6.
    asr_backend: Literal["groq", "whisperx_local"] = "groq"
    groq_api_key: str = ""
    groq_asr_model: str = "whisper-large-v3-turbo"

    # ── LLM ──────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_api_keys: str = ""
    # BR-DUB-02: tên model đọc từ env, KHÔNG hardcode trong code
    gemini_model: str = "gemini-2.5-flash"
    # Danh sách model fallback, phân cách bởi dấu phẩy. Khi model đầu bị 429/block,
    # hệ thống tự chuyển sang model tiếp theo mà không cần restart.
    # Ví dụ: gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash
    gemini_models: str = ""
    # Free Tier Gemini giới hạn ~15 RPM — tự giới hạn thấp hơn 1 chút để tránh 429
    # (doc/SETUP_GIAIDOAN5.md mục 3).
    gemini_rate_limit_rpm: int = 12

    # ── TTS ──────────────────────────────────────────────────
    # Azure Speech Service — thay cho edge-tts free trước đây (không có SLA, dễ bị
    # Microsoft chặn/thay đổi đột ngột vì không phải API chính thức).
    azure_speech_key: str = ""
    azure_speech_region: str = ""

    # ── RAG cho Socratic Tutor (BR-TUTOR-03) ─────────────────
    supabase_vector_url: str = ""
    supabase_vector_key: str = ""
    # BR-DUB-02 áp dụng tương tự cho model embedding: tên model đọc từ env.
    gemini_embedding_model: str = ""
    embedding_dimensions: int = 768
    # BR-TUTOR-04: ngưỡng cosine similarity tối thiểu — giá trị cụ thể bị mất khi
    # convert DOCX→Markdown (TODO(doc) trong business-rules.md), tạm dùng 0.7.
    rag_min_similarity: float = 0.7

    # ── UC49 nâng cấp — Hybrid semantic search cho Course Discovery ─────────
    # Test thực tế (25/09/2026, sau khi gỡ ivfflat index gây lỗi ở quy mô catalog nhỏ —
    # xem docblock `course_embeddings_embedding_idx`): khóa THẬT liên quan ra ~0.70-0.72,
    # khóa KHÔNG liên quan vẫn có similarity nền ~0.55-0.63 (do model embedding cho văn
    # bản tiếng Việt ngắn), nên 0.5 quá lỏng, gần như không lọc được gì. 0.65 tách rõ 2 nhóm.
    discovery_min_similarity: float = 0.65
    discovery_similarity_top_k: int = 6
    # Kích thước pool ứng viên lấy từ BE (đã lọc category/level/priceType) để
    # rerank bằng similarity — đủ dùng ở quy mô catalog hiện tại.
    discovery_candidate_pool_size: int = 200

    # ── Cloud storage ────────────────────────────────────────
    b2_bucket_name: str = ""
    b2_key_id: str = ""
    b2_application_key: str = ""
    b2_endpoint: str = ""

    # ── Tham số pipeline ─────────────────────────────────────
    chunk_minutes: int = 10          # BR-CHUNK-02: phân đoạn cố định 10 phút
    max_retry: int = 3               # BR-CHUNK-04: retry tối đa 3 lần
    rag_top_k: int = 5               # BR-TUTOR-04: tối đa 5 đoạn transcript
    llm_format_retry: int = 2        # BR-MAT-06: gọi lại LLM tối đa 2 lần khi sai định dạng

    # Trần vòng lặp LLM Re-summarization (BR-DUB-03) — văn bản BR gốc không có điều kiện
    # dừng, nếu làm đúng y nguyên có nguy cơ lặp vô hạn khi câu đã quá ngắn mà R vẫn > 1.3.
    # Hết số lần này mà R vẫn > 1.3 thì chấp nhận rate +30% (mức tối đa) và ghi log cảnh báo
    # cho Admin xem qua UC45/UC46 (doc/SETUP_GIAIDOAN5.md mục 4).
    max_resummarize_attempts: int = 2
    # 11/11/2026 (NCKH): câu có khung gốc NGẮN hơn ngưỡng này KHÔNG gọi LLM rút gọn — chỉ tăng tốc
    # tối đa +30%, phần dư mượn khoảng lặng phía sau (đã có xếp câu theo mốc tuyệt đối). Đo thực
    # nghiệm: 51,8% lời gọi rút gọn rơi vào câu ngắn mà rút gọn 2 lần vẫn chạm trần → tốn credit vô ích.
    # Đặt 0 để tắt (luôn rút gọn như cũ).
    min_resummarize_frame_sec: float = 2.0
    # Hiệu năng dubbing (S1): số câu tổng hợp giọng CÙNG LÚC trong 1 chunk. Azure Speech S0 cho
    # ~100 request/10 s qua REST nên 8 là an toàn; đặt 1 để quay về chạy tuần tự như cũ.
    tts_concurrency: int = 8
    # Số tiến trình FFmpeg `atempo` chạy cùng lúc (CPU-bound, máy chủ 2 vCPU).
    tempo_concurrency: int = 2
    # Mức "suy nghĩ" của Gemini cho dịch/rút gọn lời thoại (S7). Rỗng = mặc định của model (như cũ).
    # Model Gemini 3.x nhận "minimal" | "low" | "medium" | "high"; token suy nghĩ ẩn VẪN tính tiền.
    dubbing_thinking_level: str = ""
    # M2 (thử nghiệm) — giữ nhạc nền: "modal" = tách bằng Demucs trên Modal (cần token Modal);
    # rỗng = tắt (như cũ). Xem `app/services/background_music.py`.
    bgm_separation: str = ""
    bgm_modal_app: str = "lms-demucs"
    bgm_wait_timeout_sec: int = 600
    # Giữ NGUYÊN âm lượng nhạc gốc; giọng lồng tiếng được chỉnh to bằng giọng gốc thay vì hạ nhạc.
    bgm_music_volume: float = 1.0
    # Tự hạ nhạc khi có lời — chỉ bật nếu nghe thấy giọng gốc còn sót trong phần nhạc tách ra.
    bgm_ducking: bool = False
    # Mức "suy nghĩ" cho các tính năng đơn giản khác (21/11/2026). Đo thật: mặc định model suy nghĩ ~1-1,7 lần lượng chữ trả về và token này vẫn tính tiền như token ra. Rỗng = mặc định
    # của model (hành vi cũ) — đặt biến môi trường tương ứng thành rỗng để tắt từng nhóm. Gia sư hỏi đáp, Discovery, trợ lý giảng viên, giám sát thi, kế hoạch học KHÔNG đổi.
    material_thinking_level: str = "low"          # mindmap / flashcard / quiz: cấu trúc hóa từ transcript có sẵn
    quiz_explain_thinking_level: str = "low"      # giải thích đáp án quiz: ngắn, đã có đủ ngữ cảnh trong prompt
    aux_thinking_level: str = "minimal"           # đặt tiêu đề hội thoại, kiểm duyệt đánh giá: phân loại/tóm tắt rất ngắn

    # Thư mục file trung gian. Phải dọn sau mỗi job, tối đa 24 giờ (BR-STORAGE-01).
    temp_dir: str = "/tmp/lms-processing"
    intermediate_file_ttl_hours: int = 24

    # ── YouTube (UC18/UC19, app/media.py::download_youtube_audio) ────
    # BUG THẬT (05/09/2026): yt-dlp bị YouTube chặn ("Sign in to confirm you're not a bot") khi
    # tải audio nguồn từ IP datacenter/VPS thật của server production — xác nhận thật, không phải
    # lỗi cấu hình. Đã thử cookie (bỏ, cần refresh định kỳ) và proxy MIỄN PHÍ dạng datacenter của
    # Webshare (xác nhận thật KHÔNG giải quyết được — vẫn bị chặn y hệt trên 4/4 proxy đã thử).
    # Chỉ proxy RESIDENTIAL thật (trả phí, IP trông như 1 kết nối Internet nhà dân) mới có tác
    # dụng. File không tồn tại/rỗng -> không dùng proxy, tải thẳng như trước (không bắt buộc).
    # Định dạng file: xem `secrets/README.md`.
    youtube_proxy_list_path: str = "secrets/youtube_proxies.txt"

    # ── Live Classroom (F11) ─────────────────────────────────
    # F11.6 — chọn "ai đứng sau xử lý nhận diện/dịch giọng nói live" cho CẢ Translation Agent lẫn
    # Transcription Agent (app/live/providers/). Mặc định "azure" giữ hành vi y hệt trước khi có
    # provider Gemini (F11.7) — đổi qua "gemini" chỉ cần sửa biến môi trường này rồi restart
    # ai-api, không cần build lại code.
    live_translation_provider: Literal["azure", "gemini"] = "azure"
    # F11.7 — BR-DUB-02 áp dụng tương tự: tên model Gemini Live đọc từ env, KHÔNG hardcode. Đã xác
    # nhận CẢ 2 model dưới đây tồn tại thật và nhận (`bidiGenerateContent`) qua
    # `client.models.list()`/`client.models.get()` thật (01/09/2026).
    # - `gemini_live_transcribe_model`: model Live THUẦN transcription (không dịch, không tổng hợp
    #   giọng) — dùng cho "Phụ đề gốc" ĐỘC LẬP (GeminiTranscriptionProvider), rẻ/nhanh hơn 1 model
    #   đàm thoại chung vì không cần trả lời bằng audio.
    # - `gemini_live_translate_model`: model Live CÓ `translation_config` — dùng cho
    #   GeminiTranslationProvider (audio dịch + phụ đề gốc/dịch đồng bộ tuyệt đối trong 1 phiên).
    gemini_live_transcribe_model: str = "gemini-3.5-transcribe-live"
    gemini_live_translate_model: str = "gemini-3.5-live-translate-preview"


@lru_cache
def get_settings() -> Settings:
    """Cache để không đọc lại env mỗi lần gọi."""
    return Settings()


settings = get_settings()
