"""F11.6 — interface trừu tượng cho "ai đứng sau xử lý nhận diện/dịch giọng nói live", tách khỏi
`TranslationAgentSession`/`TranscriptionAgentSession` (kết nối LiveKit, hàng đợi phát audio, publish
phụ đề — dùng chung mọi provider) để về sau thêm Gemini (F11.7) mà không đụng lại phần đã test kỹ
qua Docker/LiveKit Cloud thật ở F11.3/F11.5.

Vòng đời CHIA 2 BƯỚC cố ý, không gộp làm 1 `start()`:
  1. `configure(...)` — dựng xong recognizer/phiên NHƯNG CHƯA bắt đầu nhận diện, gọi TRƯỚC khi vào
     phòng LiveKit — audio giảng viên có thể tới NGAY khi vừa subscribe được track, nơi nhận
     (`write_audio`) phải sẵn sàng từ trước đó.
  2. `begin()` — thật sự bắt đầu nhận diện liên tục, gọi SAU KHI nơi tiêu thụ kết quả đã sẵn sàng
     (với `LiveTranslationProvider`: hàng đợi phát audio đã dịch qua `_playback_loop`) — tránh sự
     kiện đầu tiên tới sớm hơn nơi xử lý nó, y hệt thứ tự cũ trong `translation_agent.py` trước khi
     tách provider (`_setup_azure_recognizer()` rồi mới `start_continuous_recognition()`).

Mọi callback (`on_recognizing`/`on_recognized`/...) có thể bị GỌI TỪ THREAD RIÊNG của SDK provider
(Azure Speech SDK gọi callback trên thread nội bộ của nó, không phải event loop asyncio chính) —
nơi gọi (Translation/TranscriptionAgentSession) chịu trách nhiệm tự marshal qua
`asyncio.run_coroutine_threadsafe`/`loop.call_soon_threadsafe` khi cần, y hệt cách đang làm với
Azure hiện tại. Bản thân provider KHÔNG được tự ý await/gọi coroutine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class TranslationResult:
    original_text: str
    translated_text: str
    latency_ms: str | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    text: str


class LiveTranslationProvider(Protocol):
    #: F11.7 — CHỈ đúng khi provider phát TỪ CHÍNH phiên dịch 1 luồng "gốc" đồng bộ tuyệt đối với
    #: bản dịch (Gemini: `input_audio_transcription` + `output_audio_transcription` cùng 1
    #: session). Azure vẫn `False` — giữ nguyên quyết định F11.5 mở rộng: phụ đề gốc của Azure chỉ
    #: đến từ `transcription_agent.py` (luồng riêng, không qua bước dịch), `TranslationAgentSession`
    #: không tự phát "gốc" khi cờ này tắt — đúng hành vi F11.3/F11.5 khi provider=azure, không đổi.
    publishes_synced_original: bool

    #: F11.7 — sample rate THẬT của audio đã dịch mà `on_synthesizing_audio` trả về — Azure luôn
    #: 16000 (`Raw16Khz16BitMonoPcm`, chốt cứng), Gemini luôn 24000 (xác nhận thật qua
    #: `mime_type='audio/pcm;rate=24000'` của `inline_data`, 01/09/2026). KHÔNG hardcode 16000 ở
    #: `TranslationAgentSession` nữa — phải tạo `AudioSource` LiveKit đúng rate này, nếu không audio
    #: phát ra sẽ sai cao độ/tốc độ (LiveKit phát THEO ĐÚNG rate khai báo lúc tạo `AudioSource`, bất
    #: kể rate thật của dữ liệu PCM đưa vào).
    output_sample_rate: int

    def configure(
        self,
        *,
        source_language: str,
        target_language: str,
        voice_name: str,
        on_recognizing: Callable[[TranslationResult], None],
        on_recognized: Callable[[TranslationResult], None],
        on_no_match: Callable[[str], None],
        on_synthesizing_audio: Callable[[bytes], None],
        on_canceled: Callable[[bool, str], None],
        on_session_started: Callable[[], None] | None = None,
    ) -> None: ...

    def begin(self) -> None: ...

    def write_audio(self, pcm_bytes: bytes) -> None: ...

    def stop(self) -> None: ...


class LiveTranscriptionProvider(Protocol):
    def configure(
        self,
        *,
        source_language: str,
        on_recognizing: Callable[[TranscriptionResult], None],
        on_recognized: Callable[[TranscriptionResult], None],
        on_no_match: Callable[[], None],
        on_canceled: Callable[[bool, str], None],
        on_session_started: Callable[[], None] | None = None,
    ) -> None: ...

    def begin(self) -> None: ...

    def write_audio(self, pcm_bytes: bytes) -> None: ...

    def stop(self) -> None: ...
