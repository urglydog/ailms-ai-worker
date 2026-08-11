"""Cấu hình AI Worker — đọc toàn bộ từ biến môi trường.

BR-DUB-02 cấm hardcode tên model LLM, nên `gemini_model` bắt buộc đến từ env.
Xem `project/be/.env.example` để biết danh sách biến.
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
    gemini_model: str = "gemini-2.0-flash"
    # Danh sách model fallback, phân cách bởi dấu phẩy. Khi model đầu bị 429/block,
    # hệ thống tự chuyển sang model tiếp theo mà không cần restart.
    # Ví dụ: gemini-2.0-flash,gemini-1.5-flash,gemini-1.5-flash-8b
    gemini_models: str = ""

    # ── TTS ──────────────────────────────────────────────────
    edge_tts_region: str = ""

    # ── RAG cho Socratic Tutor (BR-TUTOR-03) ─────────────────
    supabase_vector_url: str = ""
    supabase_vector_key: str = ""

    # ── Cloud storage ────────────────────────────────────────
    b2_bucket_name: str = ""
    b2_key_id: str = ""
    b2_application_key: str = ""

    # ── Tham số pipeline ─────────────────────────────────────
    chunk_minutes: int = 10          # BR-CHUNK-02: phân đoạn cố định 10 phút
    max_retry: int = 3               # BR-CHUNK-04: retry tối đa 3 lần
    rag_top_k: int = 5               # BR-TUTOR-04: tối đa 5 đoạn transcript
    llm_format_retry: int = 2        # BR-MAT-06: gọi lại LLM tối đa 2 lần khi sai định dạng

    # Thư mục file trung gian. Phải dọn sau mỗi job, tối đa 24 giờ (BR-STORAGE-01).
    temp_dir: str = "/tmp/lms-processing"


@lru_cache
def get_settings() -> Settings:
    """Cache để không đọc lại env mỗi lần gọi."""
    return Settings()


settings = get_settings()
