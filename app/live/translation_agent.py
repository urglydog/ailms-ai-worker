"""F11.3 (UC52) — Translation Agent: dịch giọng nói live thời gian thực qua Azure Speech
Translation, publish lại thành 1 track LiveKit riêng cho từng ngôn ngữ đích.

Kiến trúc — dùng thẳng `livekit` (rtc SDK), KHÔNG dùng `livekit-agents` framework: framework đó
thiết kế cho mô hình "worker tự đăng ký + tự nhận job mới do LiveKit server tự dispatch" (đa tiến
trình, kênh IPC riêng cho từng job — nặng, phức tạp hơn nhiều so với nhu cầu thực tế). Ở đây `be/`
đã biết CHÍNH XÁC lúc nào cần bật/tắt (học viên bấm nút — xem `LiveLanguageTrackController`),
không cần cơ chế tự dispatch nào cả. Dùng thẳng SDK giữ logic đơn giản, chạy ngay trong tiến
trình FastAPI `ai-api` hiện có (1 asyncio task/track đang ACTIVE), không cần thêm Docker service
hay tiến trình con nào — đơn giản hơn đáng kể so với dự tính ban đầu ở
`doc/FEATURE_ASSIGNMENT.md` (mục F11.3), viết lại sau khi tra cứu API thật của cả 2 SDK.

Luồng dữ liệu:
    audio giảng viên (LiveKit track) --AudioStream--> PushAudioInputStream (Azure)
    --TranslationRecognizer (dịch + tổng hợp giọng)--> sự kiện `synthesizing`
    --AudioFrame--> AudioSource --publish_track--> track LiveKit mới `translated-{targetLanguage}`

Định dạng âm thanh CHỐT CỨNG 16kHz/mono/PCM16 ở cả 2 đầu (LiveKit `AudioStream.from_track` tự
resample chiều vào, Azure `Raw16Khz16BitMonoPcm` chốt chiều ra) — không cần thư viện resample
nào thêm, không có RIFF/WAV header phải bóc.

BUG THẬT phát hiện lúc bạn test thật (31/08/2026): độ trễ giữa lúc giảng viên nói và lúc audio
dịch phát ra có thể lên tới **72 giây** (log thật: subscribe audio lúc t=0, `synthesizing` đầu
tiên — mà còn lỗi — tới tận t=+72s), xa mức "vài giây" mà BR-LIVE-08 hứa. Nghi ngờ chính: Azure
CHỈ chốt xong 1 câu (`recognized`, mới bắt đầu tổng hợp giọng) khi phát hiện giảng viên NGỪNG NÓI
đủ lâu — nói liên tục không ngắt thì Azure cứ đợi. Đã thêm log chi tiết mức DEBUG cho từng bước
(`recognizing`/`recognized`/`synthesizing`, kèm `[t+Ns]` từ lúc agent bắt đầu) + đặt cứng 2 tham
số phân đoạn của Azure để CHẶN TRÊN thời gian chờ này — cả 2 giá trị là **ước lượng ban đầu, CHƯA
qua kiểm chứng bằng tai người thật**, cần bạn tự nghe thử và báo lại nếu vẫn còn trễ nhiều hoặc
ngược lại câu bị cắt cụt quá sớm.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import azure.cognitiveservices.speech as speechsdk
from livekit import rtc

from app.config import settings

log = logging.getLogger(__name__)
# Root logger của app chỉ bật INFO (app/main.py) — set riêng logger này DEBUG để log chi tiết
# recognizing/recognized/synthesizing hiện ra trong `docker logs`, không cần đổi cấu hình toàn cục
# (tránh kéo theo log DEBUG rất ồn của các thư viện khác như httpx/uvicorn).
log.setLevel(logging.DEBUG)

_SAMPLE_RATE = 16000
_NUM_CHANNELS = 1

# Kích thước 1 khung khi PHÁT audio đã dịch (khác kích thước khung LiveKit tự chia lúc NHẬN audio
# giảng viên) — 20ms là mức phổ biến cho audio thời gian thực (WebRTC). Xem docstring
# `_capture_pcm` để biết lý do bắt buộc phải cắt nhỏ chứ không gửi nguyên cục Azure trả về.
_CAPTURE_FRAME_MS = 20
_CAPTURE_CHUNK_BYTES = int(_SAMPLE_RATE * _CAPTURE_FRAME_MS / 1000) * 2 * _NUM_CHANNELS  # = 640 byte

# Log 1 dòng "vẫn đang nhận audio giảng viên" mỗi N frame — LiveKit gửi frame theo lô nhỏ (thường
# ~10-20ms/frame ở 16kHz), nên log MỖI frame sẽ ngập log; 100 frame ~ 1-2 giây/dòng heartbeat là đủ
# để phân biệt "Azure xử lý chậm" (heartbeat vẫn đều) với "audio ngừng chảy vào" (heartbeat im bặt).
_HEARTBEAT_EVERY_N_FRAMES = 100

# Data Message topic phát phụ đề gốc + phụ đề dịch — giống cơ chế chat live (F11.4, BR-LIVE-12):
# không lưu CSDL, chỉ phát cho ai đang kết nối lúc đó. FE lọc theo `targetLanguage` để hiện đúng
# phụ đề dịch của ngôn ngữ học viên đang chọn — nhiều track (nhiều ngôn ngữ) cùng phát topic này
# cùng lúc, mỗi track tự gắn `targetLanguage` của mình vào payload.
_SUBTITLE_TOPIC = "lms.live-subtitle"


@dataclass(frozen=True)
class TranslationAgentConfig:
    track_id: int
    room_name: str
    server_url: str
    agent_token: str
    instructor_identity: str
    source_language: str
    target_language: str
    voice_name: str
    track_name: str


def _azure_target_language(voice_locale: str) -> str:
    """Azure Speech Translation nhận mã ngôn ngữ đích DẠNG NGẮN (vd "ja"), khác locale đầy đủ
    dùng trong `voice_mappings` (vd "ja-JP"). Lấy tiền tố chính đủ đúng cho đa số 148 ngôn ngữ
    đang hỗ trợ — vài trường hợp đặc biệt (vd biến thể chữ Hán giản thể/phồn thể) có thể cần ánh
    xạ riêng sau này nếu phát sinh lỗi thật, chưa có bảng đối chiếu chính thức để làm trước."""
    return voice_locale.split("-")[0]


class TranslationAgentSession:
    """1 phiên Translation Agent cho ĐÚNG 1 `LiveLanguageTrack` — vòng đời gắn với đúng track
    đó, không dùng lại cho track khác (BR-LIVE-05: mỗi track ACTIVE có agent riêng)."""

    def __init__(self, config: TranslationAgentConfig) -> None:
        self._config = config
        self._room = rtc.Room()
        self._audio_source = rtc.AudioSource(sample_rate=_SAMPLE_RATE, num_channels=_NUM_CHANNELS)
        self._push_stream: speechsdk.audio.PushAudioInputStream | None = None
        self._recognizer: speechsdk.translation.TranslationRecognizer | None = None
        self._stop_event = asyncio.Event()
        self._loop = asyncio.get_event_loop()
        self._pump_task: asyncio.Task | None = None
        self._started_at = time.monotonic()
        self._frames_received = 0
        # BUG THẬT (31/08/2026): giảng viên nói liên tục (vd phát 1 video làm nguồn) khiến Azure
        # chốt nhiều câu gần nhau — mỗi câu chốt xong bắn 1 sự kiện `synthesizing`, và trước đây
        # MỖI sự kiện tự tạo 1 task gọi `capture_frame()` RIÊNG qua `run_coroutine_threadsafe`.
        # Khi câu 2 chốt xong trong lúc câu 1 CHƯA phát hết (audio dài vài giây, phát theo đúng
        # nhịp thời gian thực), 2 task này gọi `capture_frame()` CHỒNG LÊN NHAU trên CÙNG 1
        # `AudioSource` — LiveKit không chịu được, ném `InvalidState` và agent tự dừng (đúng log
        # thật: `synthesizing` 125KB tới trong lúc câu 286KB trước còn đang phát dở). SỬA: xếp
        # hàng qua `asyncio.Queue`, CHỈ 1 task (`_playback_loop`) tiêu thụ hàng đợi tuần tự —
        # không bao giờ có 2 lệnh `capture_frame()` chạy cùng lúc nữa, câu 2 tự chờ câu 1 phát
        # xong (đúng hành vi mong muốn: nghe lần lượt, không lẫn giọng).
        self._pcm_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._playback_task: asyncio.Task | None = None

    def _elapsed(self) -> float:
        return time.monotonic() - self._started_at

    async def run(self) -> None:
        cfg = self._config
        log.info(
            "Live track %s: bat dau Translation Agent (%s -> %s, giong %s) trong phong %s",
            cfg.track_id, cfg.source_language, cfg.target_language, cfg.voice_name, cfg.room_name,
        )
        self._setup_azure_recognizer()
        local_track = rtc.LocalAudioTrack.create_audio_track(cfg.track_name, self._audio_source)

        @self._room.on("track_subscribed")
        def _on_track_subscribed(
            track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity == cfg.instructor_identity:
                log.info("Live track %s [t+%.1fs]: da subscribe duoc audio giang vien", cfg.track_id, self._elapsed())
                self._pump_task = asyncio.create_task(self._pump_instructor_audio(track))

        @self._room.on("disconnected")
        def _on_room_disconnected(reason=None) -> None:
            # Phòng vệ (31/08/2026): phòng có thể bị đóng TỪ NGOÀI — `be/` chủ động gọi
            # `deleteRoom()` khi kết thúc phiên (chống phí LiveKit oan), hoặc đơn giản là mất
            # mạng. Không tự dọn thì `run()` cứ treo mãi ở `await self._stop_event.wait()`,
            # Azure recognizer vẫn sống dù chẳng còn audio nào tới nữa.
            log.info(
                "Live track %s [t+%.1fs]: phong LiveKit bi dong tu ben ngoai (%s), tu dung agent",
                cfg.track_id, self._elapsed(), reason,
            )
            self.stop()

        try:
            await self._room.connect(cfg.server_url, cfg.agent_token)
            # source PHAI set tuong minh — mac dinh la SOURCE_UNKNOWN (proto enum index 0), FE
            # loc track dich qua `useTracks([Track.Source.Microphone])` (cung nhom voi mic that
            # cua giang vien de con chuyen doi subscribe qua lai — xem LiveLanguageControls o fe/).
            publish_options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            await self._room.local_participant.publish_track(local_track, publish_options)
            self._playback_task = asyncio.create_task(self._playback_loop())
            self._recognizer.start_continuous_recognition()

            await self._stop_event.wait()
        except Exception:
            log.exception("Live track %s: Translation Agent gap loi, dung som", cfg.track_id)
        finally:
            await self._teardown()

    def stop(self) -> None:
        """An toàn gọi từ thread khác — `synthesizing`/`canceled` của Azure SDK chạy trên thread
        riêng của SDK, không phải event loop chính."""
        self._loop.call_soon_threadsafe(self._stop_event.set)

    async def _pump_instructor_audio(self, track: rtc.Track) -> None:
        stream = rtc.AudioStream.from_track(track=track, sample_rate=_SAMPLE_RATE, num_channels=_NUM_CHANNELS)
        try:
            async for event in stream:
                if self._push_stream is not None:
                    self._push_stream.write(bytes(event.frame.data))
                self._frames_received += 1
                if self._frames_received % _HEARTBEAT_EVERY_N_FRAMES == 0:
                    log.debug(
                        "Live track %s [t+%.1fs]: van dang nhan audio giang vien (%d frame)",
                        self._config.track_id, self._elapsed(), self._frames_received,
                    )
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Live track %s: loi doc audio giang vien", self._config.track_id)
        finally:
            await stream.aclose()

    def _setup_azure_recognizer(self) -> None:
        cfg = self._config
        translation_config = speechsdk.translation.SpeechTranslationConfig(
            subscription=settings.azure_speech_key, region=settings.azure_speech_region,
        )
        translation_config.speech_recognition_language = cfg.source_language
        translation_config.add_target_language(_azure_target_language(cfg.target_language))
        # BẮT BUỘC set TRƯỚC voice_name — bản thân voice_name mới là thứ kích hoạt chế độ tổng
        # hợp giọng (speech-to-speech), set_speech_synthesis_output_format chỉ chốt định dạng.
        translation_config.voice_name = cfg.voice_name
        translation_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm
        )
        # BUG THẬT (31/08/2026): đã THỬ set Speech_SegmentationSilenceTimeoutMs +
        # Speech_SegmentationMaximumTimeMs để chặn trên độ trễ "đợi giảng viên ngừng nói" — Azure
        # từ chối thẳng kết nối ("Could not validate speech context", WebSocket 1007) chỉ sau
        # ~5 giây, TranslationRecognizer với 2 property này không hoạt động như tài liệu mô tả
        # (có thể do phiên bản SDK, hoặc 2 property này không hợp lệ khi dùng chung với chế độ
        # tổng hợp giọng speech-to-speech của TranslationRecognizer — chưa xác định chắc chắn).
        # RÚT LẠI hoàn toàn để khôi phục hoạt động — không đoán tiếp giá trị mới mà không kiểm
        # chứng được bằng tai người thật giữa mỗi lần thử. Muốn giảm độ trễ, thử lại TỪNG property
        # một, xem log DEBUG (recognizing/recognized) để so trước/sau, và cần bạn nghe thử ngay.

        push_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=_SAMPLE_RATE, bits_per_sample=16, channels=_NUM_CHANNELS,
        )
        self._push_stream = speechsdk.audio.PushAudioInputStream(stream_format=push_format)
        audio_config = speechsdk.audio.AudioConfig(stream=self._push_stream)

        self._recognizer = speechsdk.translation.TranslationRecognizer(
            translation_config=translation_config, audio_config=audio_config,
        )
        self._recognizer.recognizing.connect(self._on_recognizing)
        self._recognizer.recognized.connect(self._on_recognized)
        self._recognizer.synthesizing.connect(self._on_synthesizing)
        self._recognizer.canceled.connect(self._on_canceled)
        self._recognizer.session_started.connect(
            lambda evt: log.debug("Live track %s [t+%.1fs]: Azure session_started", cfg.track_id, self._elapsed())
        )

    def _on_recognizing(self, evt: speechsdk.translation.TranslationRecognitionEventArgs) -> None:
        """Kết quả TẠM (chưa chốt câu) — Azure liên tục cập nhật trong lúc giảng viên còn đang
        nói. Thấy dòng này đều đặn nghĩa là Azure ĐANG nhận audio bình thường, chỉ là chưa chốt
        xong câu để dịch/tổng hợp giọng — phân biệt với trường hợp audio không tới Azure."""
        if not evt.result.text:
            return
        log.debug(
            "Live track %s [t+%.1fs] dang nhan dien (tam): '%s'",
            self._config.track_id, self._elapsed(), evt.result.text,
        )

    def _on_recognized(self, evt: speechsdk.translation.TranslationRecognitionEventArgs) -> None:
        """Kết quả CHỐT (1 câu/đoạn đã xong) — đây là mốc quan trọng nhất để đo độ trễ thật: thời
        gian từ lúc giảng viên bắt đầu nói câu đó tới lúc dòng log này xuất hiện."""
        elapsed = self._elapsed()
        reason = evt.result.reason
        if reason == speechsdk.ResultReason.TranslatedSpeech:
            translations = dict(evt.result.translations) if evt.result.translations else {}
            recognition_latency_ms = self._read_property(
                evt.result, speechsdk.PropertyId.SpeechServiceResponse_RecognitionLatencyMs
            )
            log.info(
                "Live track %s [t+%.1fs] DA CHOT CAU (Azure recognition latency=%s ms): goc='%s' dich=%s",
                self._config.track_id, elapsed, recognition_latency_ms, evt.result.text, translations,
            )
            translated_text = translations.get(_azure_target_language(self._config.target_language), "")
            if evt.result.text or translated_text:
                asyncio.run_coroutine_threadsafe(
                    self._publish_subtitle(evt.result.text, translated_text), self._loop
                )
        elif reason == speechsdk.ResultReason.NoMatch:
            log.warning(
                "Live track %s [t+%.1fs] KHONG NHAN DIEN DUOC gi (NoMatch) — co the do im lang keo dai,"
                " tieng on, hoac dinh dang audio sai (%s)",
                self._config.track_id, elapsed, evt.result.no_match_details,
            )

    def _on_synthesizing(self, evt: speechsdk.translation.TranslationSynthesisEventArgs) -> None:
        """Chạy trên thread nội bộ của Azure SDK — chỉ được đụng vào event loop qua
        `run_coroutine_threadsafe`, không được `await` trực tiếp ở đây."""
        elapsed = self._elapsed()
        audio_bytes = evt.result.audio
        if not audio_bytes:
            log.debug(
                "Live track %s [t+%.1fs] synthesizing: 0 byte = tin hieu KET THUC 1 cau tong hop",
                self._config.track_id, elapsed,
            )
            return
        log.debug(
            "Live track %s [t+%.1fs] synthesizing: nhan %d byte audio da dich, xep hang phat...",
            self._config.track_id, elapsed, len(audio_bytes),
        )
        # Chỉ XẾP HÀNG — KHÔNG gọi capture_frame() trực tiếp ở đây (xem ghi chú _pcm_queue ở
        # __init__ để biết lý do bắt buộc phải qua hàng đợi tuần tự).
        self._loop.call_soon_threadsafe(self._pcm_queue.put_nowait, audio_bytes)

    def _on_canceled(self, evt: speechsdk.translation.TranslationRecognitionCanceledEventArgs) -> None:
        """BUG THẬT (31/08/2026): trước đây chỉ log rồi để agent chạy tiếp — khi Azure huỷ kết
        nối vì LỖI THẬT (vd cấu hình sai khiến server từ chối ngay), `_pump_instructor_audio` vẫn
        vô tư đẩy audio vào 1 `push_stream` không còn ai đọc, log heartbeat "vẫn đang nhận audio"
        chạy đều khiến tưởng nhầm là đang hoạt động bình thường. Lỗi thật (`CancellationReason.Error`)
        thì dừng hẳn agent luôn — thiết kế hiện tại không tự kết nối lại được."""
        reason = evt.cancellation_details.reason
        if reason == speechsdk.CancellationReason.Error:
            log.error(
                "Live track %s [t+%.1fs]: Azure Translation LOI THAT, dung agent - %s",
                self._config.track_id, self._elapsed(), evt.cancellation_details,
            )
            self.stop()
        else:
            log.info(
                "Live track %s [t+%.1fs]: Azure Translation ket thuc binh thuong (%s)",
                self._config.track_id, self._elapsed(), reason,
            )

    async def _publish_subtitle(self, original_text: str, translated_text: str) -> None:
        """Phát phụ đề gốc + dịch qua Data Message — không đi qua `_pcm_queue` vì đây là dữ liệu
        NHẸ (vài trăm byte text), không tranh chấp tài nguyên với audio nên không cần xếp hàng
        tuần tự như `capture_frame()`."""
        payload = json.dumps({
            "targetLanguage": self._config.target_language,
            "original": original_text,
            "translated": translated_text,
        })
        try:
            await self._room.local_participant.publish_data(payload, reliable=True, topic=_SUBTITLE_TOPIC)
        except Exception:
            log.exception("Live track %s [t+%.1fs]: loi phat phu de", self._config.track_id, self._elapsed())

    @staticmethod
    def _read_property(result, property_id) -> str:
        """Best-effort — không phải mọi property đều được Azure điền cho translation result,
        không để lỗi đọc property lam hong ca dong log chinh."""
        try:
            value = result.properties.get_property(property_id)
            return value if value else "?"
        except Exception:
            return "?"

    async def _playback_loop(self) -> None:
        """Tiêu thụ hàng đợi `_pcm_queue` TUẦN TỰ, từng cục audio đã dịch một — đây là nơi DUY
        NHẤT gọi `capture_frame()` trong cả class, đảm bảo không bao giờ có 2 lệnh chồng nhau
        (xem ghi chú ở `__init__`). Câu 2 tự chờ câu 1 phát xong mới tới lượt — đúng hành vi mong
        muốn khi giảng viên nói liên tục, dịch dồn lại thay vì lẫn giọng/crash."""
        try:
            while True:
                pcm_bytes = await self._pcm_queue.get()
                await self._capture_pcm(pcm_bytes)
        except asyncio.CancelledError:
            pass

    async def _capture_pcm(self, pcm_bytes: bytes) -> None:
        """BUG THẬT (31/08/2026) — Azure trả về NGUYÊN CỤC audio đã dịch cho cả 1 câu/đoạn dài
        (thấy thật trong log: 692KB ~ 21 giây audio cho 1 đoạn giảng viên nói liên tục ~18 giây
        không ngắt) — nhưng `AudioSource` của LiveKit chỉ có hàng đợi nội bộ ~1 giây
        (`queue_size_ms` mặc định). Cắt nhỏ thành từng khung ~20ms trước khi gọi
        `capture_frame()` nhiều lần — mỗi lệnh gọi nhỏ tự chờ đúng nhịp thời gian thực theo đúng
        thiết kế của `AudioSource`, không còn 1 cục khổng lồ nào cả. CHỈ được gọi từ
        `_playback_loop` (tuần tự) — không tự ý gọi hàm này từ nơi khác.
        """
        usable_len = len(pcm_bytes) - (len(pcm_bytes) % 2)
        if usable_len == 0:
            return
        try:
            for offset in range(0, usable_len, _CAPTURE_CHUNK_BYTES):
                chunk = pcm_bytes[offset : offset + _CAPTURE_CHUNK_BYTES]
                chunk_len = len(chunk) - (len(chunk) % 2)
                if chunk_len == 0:
                    continue
                samples_per_channel = chunk_len // (2 * _NUM_CHANNELS)
                frame = rtc.AudioFrame(chunk[:chunk_len], _SAMPLE_RATE, _NUM_CHANNELS, samples_per_channel)
                await self._audio_source.capture_frame(frame)
        except Exception:
            # Audio dịch tới TRỄ sau khi phòng/track LiveKit đã ở trạng thái không hợp lệ nữa (vd
            # giảng viên đã rời) cũng ném lỗi tương tự — coi đây là tín hiệu "hết dùng được nữa",
            # tự dừng agent luôn thay vì tiếp tục lãng phí quota Azure cho audio muộn.
            log.exception(
                "Live track %s [t+%.1fs]: loi publish audio da dich — tu dung agent",
                self._config.track_id, self._elapsed(),
            )
            self.stop()

    async def _teardown(self) -> None:
        cfg = self._config
        try:
            if self._recognizer is not None:
                self._recognizer.stop_continuous_recognition()
        except Exception:
            log.exception("Live track %s: loi dung Azure recognizer", cfg.track_id)
        if self._push_stream is not None:
            self._push_stream.close()
        if self._pump_task is not None:
            self._pump_task.cancel()
        if self._playback_task is not None:
            self._playback_task.cancel()
        try:
            await self._room.disconnect()
        except Exception:
            log.exception("Live track %s: loi ngat ket noi LiveKit", cfg.track_id)
        log.info(
            "Live track %s [t+%.1fs]: da dung Translation Agent, giai phong tai nguyen Azure (nhan tong %d frame)",
            cfg.track_id, self._elapsed(), self._frames_received,
        )
