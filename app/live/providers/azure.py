"""F11.6 — implementation Azure của `LiveTranslationProvider`/`LiveTranscriptionProvider`. Nguyên
xi logic Azure Speech SDK trước đây nằm thẳng trong `translation_agent.py`/`transcription_agent.py`
(F11.3/F11.5) — chỉ CHUYỂN VỊ TRÍ + bọc qua callback trung lập-provider (`base.py`), KHÔNG đổi tham
số/hành vi Azure nào.
"""

from __future__ import annotations

import logging

import azure.cognitiveservices.speech as speechsdk

from app.config import settings
from app.live.providers.base import TranscriptionResult, TranslationResult

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_NUM_CHANNELS = 1


def _azure_target_language(voice_locale: str) -> str:
    """Azure Speech Translation nhận mã ngôn ngữ đích DẠNG NGẮN (vd "ja"), khác locale đầy đủ
    dùng trong `voice_mappings` (vd "ja-JP"). Lấy tiền tố chính đủ đúng cho đa số 148 ngôn ngữ
    đang hỗ trợ — vài trường hợp đặc biệt (vd biến thể chữ Hán giản thể/phồn thể) có thể cần ánh
    xạ riêng sau này nếu phát sinh lỗi thật, chưa có bảng đối chiếu chính thức để làm trước."""
    return voice_locale.split("-")[0]


def _read_property(result, property_id) -> str:
    """Best-effort — không phải mọi property đều được Azure điền cho translation result, không để
    lỗi đọc property làm hỏng cả dòng log chính."""
    try:
        value = result.properties.get_property(property_id)
        return value if value else "?"
    except Exception:
        return "?"


def _make_push_stream() -> speechsdk.audio.PushAudioInputStream:
    push_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=_SAMPLE_RATE, bits_per_sample=16, channels=_NUM_CHANNELS,
    )
    return speechsdk.audio.PushAudioInputStream(stream_format=push_format)


class AzureTranslationProvider:
    # F11.5 mở rộng: phụ đề gốc của Azure luôn đến từ `transcription_agent.py` (luồng riêng, không
    # qua bước dịch) — xem ghi chú ở `base.py`.
    publishes_synced_original = False
    # `Raw16Khz16BitMonoPcm` chốt cứng ở `set_speech_synthesis_output_format` bên dưới.
    output_sample_rate = _SAMPLE_RATE

    def __init__(self) -> None:
        self._push_stream: speechsdk.audio.PushAudioInputStream | None = None
        self._recognizer: speechsdk.translation.TranslationRecognizer | None = None
        self._target_language_code = ""

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
        self._target_language_code = _azure_target_language(target_language)
        translation_config = speechsdk.translation.SpeechTranslationConfig(
            subscription=settings.azure_speech_key, region=settings.azure_speech_region,
        )
        translation_config.speech_recognition_language = source_language
        translation_config.add_target_language(self._target_language_code)
        # BẮT BUỘC set TRƯỚC voice_name — bản thân voice_name mới là thứ kích hoạt chế độ tổng
        # hợp giọng (speech-to-speech), set_speech_synthesis_output_format chỉ chốt định dạng.
        translation_config.voice_name = voice_name
        translation_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm
        )
        # BUG THẬT (31/08/2026): đã THỬ set Speech_SegmentationSilenceTimeoutMs +
        # Speech_SegmentationMaximumTimeMs để chặn trên độ trễ "đợi giảng viên ngừng nói" — Azure
        # từ chối thẳng kết nối ("Could not validate speech context", WebSocket 1007) chỉ sau ~5
        # giây. RÚT LẠI hoàn toàn để khôi phục hoạt động — muốn thử lại, đổi TỪNG property một và
        # nghe thử ngay bằng tai người thật giữa mỗi lần đổi (xem lịch sử ở translation_agent.py
        # trước khi tách provider — git blame nếu cần đối chiếu giá trị đã thử).

        self._push_stream = _make_push_stream()
        audio_config = speechsdk.audio.AudioConfig(stream=self._push_stream)

        self._recognizer = speechsdk.translation.TranslationRecognizer(
            translation_config=translation_config, audio_config=audio_config,
        )

        def _wrap_recognizing(evt) -> None:
            if not evt.result.text:
                return
            translations = dict(evt.result.translations) if evt.result.translations else {}
            on_recognizing(TranslationResult(
                original_text=evt.result.text,
                translated_text=translations.get(self._target_language_code, ""),
            ))

        def _wrap_recognized(evt) -> None:
            reason = evt.result.reason
            if reason == speechsdk.ResultReason.TranslatedSpeech:
                translations = dict(evt.result.translations) if evt.result.translations else {}
                on_recognized(TranslationResult(
                    original_text=evt.result.text,
                    translated_text=translations.get(self._target_language_code, ""),
                    latency_ms=_read_property(
                        evt.result, speechsdk.PropertyId.SpeechServiceResponse_RecognitionLatencyMs
                    ),
                ))
            elif reason == speechsdk.ResultReason.NoMatch:
                on_no_match(str(evt.result.no_match_details))

        def _wrap_synthesizing(evt) -> None:
            on_synthesizing_audio(evt.result.audio or b"")

        def _wrap_canceled(evt) -> None:
            is_error = evt.cancellation_details.reason == speechsdk.CancellationReason.Error
            on_canceled(is_error, str(evt.cancellation_details))

        self._recognizer.recognizing.connect(_wrap_recognizing)
        self._recognizer.recognized.connect(_wrap_recognized)
        self._recognizer.synthesizing.connect(_wrap_synthesizing)
        self._recognizer.canceled.connect(_wrap_canceled)
        if on_session_started is not None:
            self._recognizer.session_started.connect(lambda evt: on_session_started())

    def begin(self) -> None:
        if self._recognizer is not None:
            self._recognizer.start_continuous_recognition()

    def write_audio(self, pcm_bytes: bytes) -> None:
        if self._push_stream is not None:
            self._push_stream.write(pcm_bytes)

    def stop(self) -> None:
        try:
            if self._recognizer is not None:
                self._recognizer.stop_continuous_recognition()
        except Exception:
            log.exception("AzureTranslationProvider: loi khi dung recognizer")
        if self._push_stream is not None:
            self._push_stream.close()


class AzureTranscriptionProvider:
    def __init__(self) -> None:
        self._push_stream: speechsdk.audio.PushAudioInputStream | None = None
        self._recognizer: speechsdk.SpeechRecognizer | None = None

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
        speech_config = speechsdk.SpeechConfig(
            subscription=settings.azure_speech_key, region=settings.azure_speech_region,
        )
        speech_config.speech_recognition_language = source_language

        self._push_stream = _make_push_stream()
        audio_config = speechsdk.audio.AudioConfig(stream=self._push_stream)

        self._recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        def _wrap_recognizing(evt) -> None:
            if not evt.result.text:
                return
            on_recognizing(TranscriptionResult(text=evt.result.text))

        def _wrap_recognized(evt) -> None:
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
                on_recognized(TranscriptionResult(text=evt.result.text))
            elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                on_no_match()

        def _wrap_canceled(evt) -> None:
            is_error = evt.cancellation_details.reason == speechsdk.CancellationReason.Error
            on_canceled(is_error, str(evt.cancellation_details))

        self._recognizer.recognizing.connect(_wrap_recognizing)
        self._recognizer.recognized.connect(_wrap_recognized)
        self._recognizer.canceled.connect(_wrap_canceled)
        if on_session_started is not None:
            self._recognizer.session_started.connect(lambda evt: on_session_started())

    def begin(self) -> None:
        if self._recognizer is not None:
            self._recognizer.start_continuous_recognition()

    def write_audio(self, pcm_bytes: bytes) -> None:
        if self._push_stream is not None:
            self._push_stream.write(pcm_bytes)

    def stop(self) -> None:
        try:
            if self._recognizer is not None:
                self._recognizer.stop_continuous_recognition()
        except Exception:
            log.exception("AzureTranscriptionProvider: loi khi dung recognizer")
        if self._push_stream is not None:
            self._push_stream.close()
