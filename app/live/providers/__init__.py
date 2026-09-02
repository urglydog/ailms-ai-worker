"""F11.6 — factory chọn provider theo `settings.live_translation_provider` (mặc định "azure", đổi
qua biến môi trường `LIVE_TRANSLATION_PROVIDER`, không cần build lại code). Thêm Gemini (F11.7)
chỉ cần thêm 1 nhánh ở đây + 1 file `gemini.py` mới cạnh `azure.py` — không đụng gì tới
`TranslationAgentSession`/`TranscriptionAgentSession`.
"""

from __future__ import annotations

from app.config import settings
from app.live.providers.azure import AzureTranscriptionProvider, AzureTranslationProvider
from app.live.providers.base import (
    LiveTranscriptionProvider,
    LiveTranslationProvider,
    TranscriptionResult,
    TranslationResult,
)

__all__ = [
    "LiveTranslationProvider",
    "LiveTranscriptionProvider",
    "TranslationResult",
    "TranscriptionResult",
    "make_translation_provider",
    "make_transcription_provider",
]


def make_translation_provider() -> LiveTranslationProvider:
    if settings.live_translation_provider == "azure":
        return AzureTranslationProvider()
    if settings.live_translation_provider == "gemini":
        # Import trễ (F11.7) — tránh bắt buộc cài `google-genai` khi vẫn chỉ dùng Azure (mặc định),
        # khớp tinh thần "tắt mặc định, không ảnh hưởng ai chưa bật".
        from app.live.providers.gemini import GeminiTranslationProvider

        return GeminiTranslationProvider()
    raise ValueError(f"LIVE_TRANSLATION_PROVIDER khong ho tro: {settings.live_translation_provider!r}")


def make_transcription_provider() -> LiveTranscriptionProvider:
    if settings.live_translation_provider == "azure":
        return AzureTranscriptionProvider()
    if settings.live_translation_provider == "gemini":
        from app.live.providers.gemini import GeminiTranscriptionProvider

        return GeminiTranscriptionProvider()
    raise ValueError(f"LIVE_TRANSLATION_PROVIDER khong ho tro: {settings.live_translation_provider!r}")
