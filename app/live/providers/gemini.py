"""F11.7 — implementation Gemini Live của `LiveTranslationProvider`/`LiveTranscriptionProvider`
(tắt mặc định — `LIVE_TRANSLATION_PROVIDER=gemini` để bật, xem `app/config.py`).

Toàn bộ field/model dưới đây đã KIỂM CHỨNG THẬT bằng script gọi trực tiếp `google-genai` (SDK thật,
API key thật của dự án) ngày 01/09/2026 — KHÔNG đoán theo tài liệu suông. Bài học từ vụ
`Speech_SegmentationSilenceTimeoutMs` của Azure (xem `translation_agent.py`, thử mà không kiểm
chứng khiến Azure từ chối thẳng kết nối) là PHẢI xác nhận bằng kết nối thật trước khi tin.

Đã xác nhận thật:
  - `models/gemini-3.5-transcribe-live`, `models/gemini-3.1-flash-live-preview`,
    `models/gemini-3.5-live-translate-preview` đều tồn tại và hỗ trợ `bidiGenerateContent` (Live
    API) qua `client.models.list()`/`client.models.get()`.
  - `input_audio_transcription` hoạt động ĐỘC LẬP, không cần bật `translation_config` (dùng cho
    `GeminiTranscriptionProvider` — model transcription THUẦN, rẻ/nhanh hơn model đàm thoại chung
    vì không cần trả lời bằng audio).
  - Gemini TỰ PHÁT HIỆN điểm dừng nói bằng VAD phía server, giống hệt cơ chế tự phân đoạn của Azure
    `TranslationRecognizer` (mà pipeline live dubbing đã phụ thuộc từ F11.3) — gửi audio LIÊN TỤC,
    KHÔNG BAO GIỜ cần gọi `audio_stream_end` giữa các câu (chỉ cần lúc dừng hẳn agent). Xác nhận
    bằng cách gửi 2 câu cách nhau 2 giây im lặng, không gọi `audio_stream_end`: vẫn nhận đúng
    `input_transcription` (chốt câu 1) rồi `interim_input_transcription` reset sạch cho câu 2.
  - `server_content.interim_input_transcription.text` — model transcription THUẦN (không dịch) trả
    về chữ TĂNG DẦN qua nhiều sự kiện (giống hệt `recognizing` của Azure). Model DỊCH (bật
    `translation_config`) KHÔNG trả interim này — chỉ có các cụm "chốt" ngắn liên tiếp (xem dưới).
  - `server_content.input_transcription.text` — chữ CHỐT. Ở model transcription thuần: 1 lần/câu
    (giống `recognized`). Ở model dịch: NHIỀU cụm ngắn liên tiếp trong 1 câu dài (Google tự chia
    nhỏ để giảm độ trễ dịch — xác nhận thật: câu "Hello everyone, welcome to..." (12 từ) trả về 4
    cụm `input_transcription` riêng biệt, xen kẽ với 4 cụm `output_transcription` tương ứng).
  - `server_content.output_transcription.text` — CHỈ có ở model dịch (cần
    `output_audio_transcription` + `translation_config`) — chữ DỊCH, cùng nhịp cụm ngắn như trên.
  - `server_content.model_turn.parts[].inline_data` — audio đã dịch, `mime_type` xác nhận THẬT là
    `"audio/pcm;rate=24000"` (KHÁC 16kHz của Azure — xem `LiveTranslationProvider.output_sample_rate`
    ở `base.py`, và cách `TranslationAgentSession` dùng giá trị này để tạo đúng `AudioSource`).
  - `TranslationConfig.target_language_code` nhận cả mã ngắn ("vi") lẫn locale đầy đủ ("vi-VN")
    không lỗi khi connect — dùng mã ngắn cho khớp ví dụ chính thức của Google.
  - `AudioTranscriptionConfig.language_codes=["en-US"]`/`["en"]` đều connect được, không bị từ
    chối — dùng nguyên locale đang lưu (khớp `source_language` truyền vào, không cần rút gọn).

CHƯA kiểm chứng: chất lượng/độ trễ thật khi chạy qua LiveKit với audio giảng viên thật (script kiểm
chứng trên gọi thẳng SDK, KHÔNG qua LiveKit) — cần bạn tự bật `LIVE_TRANSLATION_PROVIDER=gemini`,
join 1 phiên live thật, và tự nghe/đọc thử trước khi coi đây là production-ready (F11.8 sẽ so sánh
độ trễ Azure/Gemini bằng số đo thật, không đoán).

Khác biệt kiến trúc quan trọng so với Azure (`azure.py`): Azure Speech SDK gọi callback từ THREAD
RIÊNG của nó (không phải asyncio) nên session phải `run_coroutine_threadsafe`/`call_soon_threadsafe`
để quay lại event loop. `google-genai` Live API là ASYNCIO THUẦN (`client.aio.live.connect`,
WebSocket 2 chiều) — provider ở đây KHÔNG cần marshal qua thread nào cả, chạy thẳng trên CÙNG event
loop với Translation/TranscriptionAgentSession (gọi `run_coroutine_threadsafe` từ chính thread của
event loop đó vẫn AN TOÀN — API cho phép gọi từ bất kỳ thread nào, kể cả thread của loop — nên
KHÔNG cần sửa gì ở 2 class Session, chúng vẫn dùng chung logic marshal viết cho Azure).
"""

from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types

from app.config import settings
from app.live.providers.base import TranscriptionResult, TranslationResult

log = logging.getLogger(__name__)

# CHIỀU VÀO (audio giảng viên) — xác nhận thật hoạt động đúng ở 16kHz, khớp `_INPUT_SAMPLE_RATE`
# bên `translation_agent.py`/`transcription_agent.py` (LiveKit luôn resample về giá trị này).
_INPUT_SAMPLE_RATE = 16000
_INPUT_MIME_TYPE = f"audio/pcm;rate={_INPUT_SAMPLE_RATE}"
# CHIỀU RA (audio đã dịch, chỉ GeminiTranslationProvider) — xác nhận thật qua mime_type trả về.
_OUTPUT_SAMPLE_RATE = 24000
# Gửi audio vào Gemini theo khung ~100ms (khuyến nghị chính thức) thay vì đẩy thẳng từng khung nhỏ
# LiveKit tự chia (~10-20ms) — gom qua hàng đợi giống hệt kiểu `_pcm_queue`/`_playback_loop` đã
# dùng cho chiều phát ở `translation_agent.py`, chỉ khác chiều (gom vào thay vì gom ra).
_INPUT_CHUNK_MS = 100
_INPUT_CHUNK_BYTES = int(_INPUT_SAMPLE_RATE * _INPUT_CHUNK_MS / 1000) * 2  # mono 16-bit = 3200 byte


def _gemini_target_language(locale: str) -> str:
    """Cùng quy tắc rút gọn với Azure (`_azure_target_language` ở azure.py) — ví dụ chính thức của
    Gemini dùng mã ngắn (vd "vi", "ja"); đã xác nhận connect được với cả 2 dạng nhưng theo mã ngắn
    cho khớp tài liệu."""
    return locale.split("-")[0]


async def _drain_audio_queue(queue: asyncio.Queue[bytes], session) -> None:
    """Dùng chung cho cả 2 provider — gom byte thành khung ~100ms rồi gửi qua `send_realtime_input`.
    CHỈ được chạy như 1 task riêng (song song với vòng lặp `receive()`) — `send_realtime_input` và
    `receive()` là 2 hướng độc lập của cùng 1 kết nối WebSocket, không tranh chấp nhau."""
    buffer = bytearray()
    try:
        while True:
            chunk = await queue.get()
            buffer.extend(chunk)
            while len(buffer) >= _INPUT_CHUNK_BYTES:
                send_chunk = bytes(buffer[:_INPUT_CHUNK_BYTES])
                del buffer[:_INPUT_CHUNK_BYTES]
                await session.send_realtime_input(audio=types.Blob(data=send_chunk, mime_type=_INPUT_MIME_TYPE))
    except asyncio.CancelledError:
        pass


class GeminiTranscriptionProvider:
    """F11.7 — thay `AzureTranscriptionProvider` khi `LIVE_TRANSLATION_PROVIDER=gemini`, dùng cho
    "Phụ đề gốc" ĐỘC LẬP (không ai chọn dịch vẫn có, xem `transcription_agent.py`). Model
    THUẦN transcription (`settings.gemini_live_transcribe_model`) — KHÔNG bật `translation_config`,
    KHÔNG trả audio (`response_modalities=[TEXT]`, rẻ/nhanh hơn model đàm thoại chung)."""

    def __init__(self) -> None:
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._source_language = ""
        self._on_recognizing = None
        self._on_recognized = None
        self._on_canceled = None
        self._on_session_started = None

    def configure(
        self,
        *,
        source_language: str,
        on_recognizing,
        on_recognized,
        on_no_match,
        on_canceled,
        on_session_started=None,
    ) -> None:
        # `on_no_match` (Protocol yêu cầu) — Gemini Live không có khái niệm "NoMatch" tường minh
        # như Azure, không có gì để gọi callback này — giữ tham số cho khớp interface, cố tình
        # không dùng.
        self._source_language = source_language
        self._on_recognizing = on_recognizing
        self._on_recognized = on_recognized
        self._on_canceled = on_canceled
        self._on_session_started = on_session_started

    def begin(self) -> None:
        self._task = asyncio.create_task(self._run())

    def write_audio(self, pcm_bytes: bytes) -> None:
        self._audio_queue.put_nowait(pcm_bytes)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        client = genai.Client(api_key=settings.gemini_api_key)
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            input_audio_transcription=types.AudioTranscriptionConfig(
                language_codes=[self._source_language] if self._source_language else None,
            ),
        )
        try:
            async with client.aio.live.connect(
                model=settings.gemini_live_transcribe_model, config=config
            ) as session:
                if self._on_session_started is not None:
                    self._on_session_started()
                send_task = asyncio.create_task(_drain_audio_queue(self._audio_queue, session))
                try:
                    async for message in session.receive():
                        self._handle_message(message)
                finally:
                    send_task.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("GeminiTranscriptionProvider: loi ket noi/nhan dien")
            if self._on_canceled is not None:
                self._on_canceled(True, str(exc))

    def _handle_message(self, message) -> None:
        sc = message.server_content
        if sc is None:
            return
        if sc.interim_input_transcription and sc.interim_input_transcription.text and self._on_recognizing:
            self._on_recognizing(TranscriptionResult(text=sc.interim_input_transcription.text))
        if sc.input_transcription and sc.input_transcription.text and self._on_recognized:
            self._on_recognized(TranscriptionResult(text=sc.input_transcription.text))


class GeminiTranslationProvider:
    """F11.7 — thay `AzureTranslationProvider` khi `LIVE_TRANSLATION_PROVIDER=gemini`. Model DỊCH
    (`settings.gemini_live_translate_model`) bật CẢ `input_audio_transcription` VÀ
    `output_audio_transcription` CÙNG `translation_config` trong 1 phiên — audio dịch + phụ đề gốc
    + phụ đề dịch đều từ CHÍNH phiên này, đồng bộ tuyệt đối (lý do chính khiến F11.7 tồn tại — xem
    `publishes_synced_original` và `_publish_original_subtitle` ở `translation_agent.py`)."""

    publishes_synced_original = True
    output_sample_rate = _OUTPUT_SAMPLE_RATE

    def __init__(self) -> None:
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._source_language = ""
        self._target_language_code = ""
        self._on_recognizing = None
        self._on_recognized = None
        self._on_synthesizing_audio = None
        self._on_canceled = None
        self._on_session_started = None

    def configure(
        self,
        *,
        source_language: str,
        target_language: str,
        voice_name: str,
        on_recognizing,
        on_recognized,
        on_no_match,
        on_synthesizing_audio,
        on_canceled,
        on_session_started=None,
    ) -> None:
        # `voice_name`/`on_no_match` (Protocol yêu cầu, khớp chữ ký AzureTranslationProvider) —
        # KHÔNG dùng `voice_name` ở đây: giá trị này đến từ danh mục giọng Azure
        # (`useVoiceOptions()`/BR-LIVE voice_mappings phía fe/), hoàn toàn KHÁC danh mục giọng của
        # Gemini — truyền thẳng vào sẽ sai/không hợp lệ. Model dịch dùng giọng mặc định của chính
        # nó cho tới khi có yêu cầu thật cần chọn giọng riêng theo Gemini (chưa có ở F11.7).
        # `on_no_match` — Gemini không có khái niệm "NoMatch" tường minh, không có gì để gọi.
        self._source_language = source_language
        self._target_language_code = _gemini_target_language(target_language)
        self._on_recognizing = on_recognizing
        self._on_recognized = on_recognized
        self._on_synthesizing_audio = on_synthesizing_audio
        self._on_canceled = on_canceled
        self._on_session_started = on_session_started

    def begin(self) -> None:
        self._task = asyncio.create_task(self._run())

    def write_audio(self, pcm_bytes: bytes) -> None:
        self._audio_queue.put_nowait(pcm_bytes)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        client = genai.Client(api_key=settings.gemini_api_key)
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=types.AudioTranscriptionConfig(
                language_codes=[self._source_language] if self._source_language else None,
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            translation_config=types.TranslationConfig(target_language_code=self._target_language_code),
        )
        try:
            async with client.aio.live.connect(
                model=settings.gemini_live_translate_model, config=config
            ) as session:
                if self._on_session_started is not None:
                    self._on_session_started()
                send_task = asyncio.create_task(_drain_audio_queue(self._audio_queue, session))
                try:
                    async for message in session.receive():
                        self._handle_message(message)
                finally:
                    send_task.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("GeminiTranslationProvider: loi ket noi/dich")
            if self._on_canceled is not None:
                self._on_canceled(True, str(exc))

    def _handle_message(self, message) -> None:
        """BUG THẬT xác nhận qua smoke test (01/09/2026): model DỊCH không trả
        `interim_input_transcription` (khác model transcription thuần) — `input_transcription` và
        `output_transcription` tới thành CÁC CỤM NGẮN liên tiếp, KHÔNG PHẢI 1 câu tăng dần. Coi mỗi
        cụm là 1 sự kiện "chốt" độc lập (`on_recognized`), KHÔNG dùng `on_recognizing` cho model
        này — gọi nhầm sẽ không sai chức năng (2 callback publish cùng cách ở tầng session) nhưng
        sai ý nghĩa log ("tạm" vs "chốt")."""
        sc = message.server_content
        if sc is None:
            return
        if sc.input_transcription and sc.input_transcription.text and self._on_recognized:
            self._on_recognized(TranslationResult(original_text=sc.input_transcription.text, translated_text=""))
        if sc.output_transcription and sc.output_transcription.text and self._on_recognized:
            self._on_recognized(TranslationResult(original_text="", translated_text=sc.output_transcription.text))
        if sc.model_turn and self._on_synthesizing_audio:
            for part in sc.model_turn.parts:
                if part.inline_data and part.inline_data.data:
                    self._on_synthesizing_audio(part.inline_data.data)
