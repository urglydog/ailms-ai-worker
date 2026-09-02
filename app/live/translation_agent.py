"""F11.3 (UC52) — Translation Agent: dịch giọng nói live thời gian thực, publish lại thành 1 track
LiveKit riêng cho từng ngôn ngữ đích.

Kiến trúc — dùng thẳng `livekit` (rtc SDK), KHÔNG dùng `livekit-agents` framework: framework đó
thiết kế cho mô hình "worker tự đăng ký + tự nhận job mới do LiveKit server tự dispatch" (đa tiến
trình, kênh IPC riêng cho từng job — nặng, phức tạp hơn nhiều so với nhu cầu thực tế). Ở đây `be/`
đã biết CHÍNH XÁC lúc nào cần bật/tắt (học viên bấm nút — xem `LiveLanguageTrackController`),
không cần cơ chế tự dispatch nào cả. Dùng thẳng SDK giữ logic đơn giản, chạy ngay trong tiến
trình FastAPI `ai-api` hiện có (1 asyncio task/track đang ACTIVE), không cần thêm Docker service
hay tiến trình con nào — đơn giản hơn đáng kể so với dự tính ban đầu ở
`doc/FEATURE_ASSIGNMENT.md` (mục F11.3), viết lại sau khi tra cứu API thật của cả 2 SDK.

Luồng dữ liệu:
    audio giảng viên (LiveKit track) --AudioStream--> provider.write_audio()
    --nhận diện + dịch + tổng hợp giọng--> on_synthesizing_audio
    --AudioFrame--> AudioSource --publish_track--> track LiveKit mới `translated-{targetLanguage}`

Định dạng âm thanh: CHIỀU VÀO (audio giảng viên) luôn 16kHz/mono/PCM16 bất kể provider nào (LiveKit
`AudioStream` tự resample) — không cần thư viện resample nào thêm, không có RIFF/WAV header phải
bóc. CHIỀU RA (audio đã dịch) phụ thuộc provider: Azure 16kHz (`Raw16Khz16BitMonoPcm`, chốt cứng),
Gemini 24kHz (xác nhận thật qua `mime_type='audio/pcm;rate=24000'`, F11.7, 01/09/2026) — xem
`LiveTranslationProvider.output_sample_rate` (`app/live/providers/base.py`).

BUG THẬT phát hiện lúc bạn test thật (31/08/2026): độ trễ giữa lúc giảng viên nói và lúc audio
dịch phát ra có thể lên tới **72 giây** (log thật: subscribe audio lúc t=0, `synthesizing` đầu
tiên — mà còn lỗi — tới tận t=+72s), xa mức "vài giây" mà BR-LIVE-08 hứa. Nghi ngờ chính: Azure
CHỈ chốt xong 1 câu (`recognized`, mới bắt đầu tổng hợp giọng) khi phát hiện giảng viên NGỪNG NÓI
đủ lâu — nói liên tục không ngắt thì Azure cứ đợi. Đã thêm log chi tiết mức DEBUG cho từng bước
(`recognizing`/`recognized`/`synthesizing`, kèm `[t+Ns]` từ lúc agent bắt đầu).

F11.6 (01/09/2026) — phần "ai đứng sau xử lý dịch" (trước đây gọi thẳng Azure SDK trong file này)
đã tách ra `app/live/providers/` (interface `LiveTranslationProvider` + implementation
`AzureTranslationProvider`) để chuẩn bị thêm Gemini (F11.7) mà không đụng lại phần kết nối
LiveKit/hàng đợi phát audio đã test kỹ ở đây — bản thân class `TranslationAgentSession` KHÔNG đổi
hành vi, chỉ đổi "ai cung cấp kết quả nhận diện/dịch" cho nó.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from livekit import rtc

from app.live.providers import TranslationResult, make_translation_provider

log = logging.getLogger(__name__)
# Root logger của app chỉ bật INFO (app/main.py) — set riêng logger này DEBUG để log chi tiết
# recognizing/recognized/synthesizing hiện ra trong `docker logs`, không cần đổi cấu hình toàn cục
# (tránh kéo theo log DEBUG rất ồn của các thư viện khác như httpx/uvicorn).
log.setLevel(logging.DEBUG)

# Sample rate NHẬN audio giảng viên — CỐ ĐỊNH bất kể provider nào (cả Azure lẫn Gemini đều nhận
# audio vào ở 16kHz, xác nhận thật với Gemini Live API qua smoke test 01/09/2026: kết nối +
# transcription vẫn đúng khi gửi `mime_type="audio/pcm;rate=16000"`). Khác sample rate audio PHÁT
# RA (dịch xong) — cái đó phụ thuộc provider, xem `_output_sample_rate` trong `__init__`.
_INPUT_SAMPLE_RATE = 16000
_NUM_CHANNELS = 1

# Kích thước 1 khung khi PHÁT audio đã dịch (khác kích thước khung LiveKit tự chia lúc NHẬN audio
# giảng viên) — 20ms là mức phổ biến cho audio thời gian thực (WebRTC). Xem docstring
# `_capture_pcm` để biết lý do bắt buộc phải cắt nhỏ chứ không gửi nguyên cục provider trả về. Kích
# thước byte tính RA TỪ sample rate thật của provider (`_output_sample_rate`) — KHÔNG hardcode
# 16000 nữa (F11.7): Gemini trả audio dịch ở 24kHz, tính sai byte/khung sẽ làm audio bị méo tốc độ.
_CAPTURE_FRAME_MS = 20

# Log 1 dòng "vẫn đang nhận audio giảng viên" mỗi N frame — LiveKit gửi frame theo lô nhỏ (thường
# ~10-20ms/frame ở 16kHz), nên log MỖI frame sẽ ngập log; 100 frame ~ 1-2 giây/dòng heartbeat là đủ
# để phân biệt "provider xử lý chậm" (heartbeat vẫn đều) với "audio ngừng chảy vào" (heartbeat im
# bặt).
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


class TranslationAgentSession:
    """1 phiên Translation Agent cho ĐÚNG 1 `LiveLanguageTrack` — vòng đời gắn với đúng track
    đó, không dùng lại cho track khác (BR-LIVE-05: mỗi track ACTIVE có agent riêng)."""

    def __init__(self, config: TranslationAgentConfig) -> None:
        self._config = config
        self._room = rtc.Room()
        self._provider = make_translation_provider()
        # F11.7 — AudioSource PHẢI khai đúng sample rate audio dịch THẬT của provider (16000 Azure,
        # 24000 Gemini) — khai sai thì LiveKit vẫn phát được nhưng SAI tốc độ/cao độ (không lỗi rõ
        # ràng, chỉ nghe "ma quái" — dễ tưởng nhầm lỗi audio khác).
        self._output_sample_rate = self._provider.output_sample_rate
        self._capture_chunk_bytes = int(self._output_sample_rate * _CAPTURE_FRAME_MS / 1000) * 2 * _NUM_CHANNELS
        self._audio_source = rtc.AudioSource(sample_rate=self._output_sample_rate, num_channels=_NUM_CHANNELS)
        self._stop_event = asyncio.Event()
        self._loop = asyncio.get_event_loop()
        self._pump_task: asyncio.Task | None = None
        self._started_at = time.monotonic()
        self._frames_received = 0
        # BUG THẬT (31/08/2026): giảng viên nói liên tục (vd phát 1 video làm nguồn) khiến provider
        # chốt nhiều câu gần nhau — mỗi câu chốt xong bắn 1 sự kiện `on_synthesizing_audio`, và
        # trước đây MỖI sự kiện tự tạo 1 task gọi `capture_frame()` RIÊNG qua
        # `run_coroutine_threadsafe`. Khi câu 2 chốt xong trong lúc câu 1 CHƯA phát hết (audio dài
        # vài giây, phát theo đúng nhịp thời gian thực), 2 task này gọi `capture_frame()` CHỒNG LÊN
        # NHAU trên CÙNG 1 `AudioSource` — LiveKit không chịu được, ném `InvalidState` và agent tự
        # dừng (đúng log thật: sự kiện 125KB tới trong lúc câu 286KB trước còn đang phát dở). SỬA:
        # xếp hàng qua `asyncio.Queue`, CHỈ 1 task (`_playback_loop`) tiêu thụ hàng đợi tuần tự —
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
        self._setup_provider()
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
            # provider vẫn sống dù chẳng còn audio nào tới nữa.
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
            # begin() bắt đầu nhận diện liên tục — gọi SAU KHI playback_task đã sẵn sàng tiêu thụ
            # audio dịch, y hệt thứ tự cũ (`start_continuous_recognition()` gọi sau cùng) trước
            # khi tách provider (xem docstring `base.py`).
            self._provider.begin()

            await self._stop_event.wait()
        except Exception:
            log.exception("Live track %s: Translation Agent gap loi, dung som", cfg.track_id)
        finally:
            await self._teardown()

    def stop(self) -> None:
        """An toàn gọi từ thread khác — callback provider (vd Azure SDK) chạy trên thread riêng,
        không phải event loop chính."""
        self._loop.call_soon_threadsafe(self._stop_event.set)

    async def _pump_instructor_audio(self, track: rtc.Track) -> None:
        stream = rtc.AudioStream.from_track(track=track, sample_rate=_INPUT_SAMPLE_RATE, num_channels=_NUM_CHANNELS)
        try:
            async for event in stream:
                self._provider.write_audio(bytes(event.frame.data))
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

    def _setup_provider(self) -> None:
        cfg = self._config
        self._provider.configure(
            source_language=cfg.source_language,
            target_language=cfg.target_language,
            voice_name=cfg.voice_name,
            on_recognizing=self._on_recognizing,
            on_recognized=self._on_recognized,
            on_no_match=self._on_no_match,
            on_synthesizing_audio=self._on_synthesizing_audio,
            on_canceled=self._on_canceled,
            on_session_started=lambda: log.debug(
                "Live track %s [t+%.1fs]: provider session_started", cfg.track_id, self._elapsed()
            ),
        )

    def _on_recognizing(self, result: TranslationResult) -> None:
        """Kết quả TẠM (chưa chốt câu) — provider liên tục cập nhật trong lúc giảng viên còn đang
        nói. Thấy dòng này đều đặn nghĩa là audio ĐANG được nhận bình thường, chỉ là chưa chốt
        xong câu để dịch/tổng hợp giọng — phân biệt với trường hợp audio không tới nơi.

        F11.5 mở rộng: có phụ đề dịch ngay ở kết quả tạm (xác nhận từ sample chính thức của
        Microsoft cho Azure) — dùng để phát phụ đề DỊCH kiểu "chạy chữ" (giống YouTube live), chạy
        song song gần đồng bộ với phụ đề GỐC (luồng riêng, xem `transcription_agent.py`) thay vì
        đợi tới lúc chốt câu mới hiện, trễ hẳn so với phụ đề gốc."""
        log.debug(
            "Live track %s [t+%.1fs] dang nhan dien (tam): '%s'",
            self._config.track_id, self._elapsed(), result.original_text,
        )
        if result.translated_text:
            asyncio.run_coroutine_threadsafe(self._publish_translation_subtitle(result.translated_text), self._loop)
        if self._provider.publishes_synced_original and result.original_text:
            asyncio.run_coroutine_threadsafe(self._publish_original_subtitle(result.original_text), self._loop)

    def _on_recognized(self, result: TranslationResult) -> None:
        """Kết quả CHỐT (1 câu/đoạn đã xong) — đây là mốc quan trọng nhất để đo độ trễ thật: thời
        gian từ lúc giảng viên bắt đầu nói câu đó tới lúc dòng log này xuất hiện."""
        log.info(
            "Live track %s [t+%.1fs] DA CHOT CAU (provider=%s, latency=%s ms): goc='%s' dich='%s'",
            self._config.track_id, self._elapsed(), type(self._provider).__name__, result.latency_ms,
            result.original_text, result.translated_text,
        )
        if result.translated_text:
            asyncio.run_coroutine_threadsafe(self._publish_translation_subtitle(result.translated_text), self._loop)
        if self._provider.publishes_synced_original and result.original_text:
            asyncio.run_coroutine_threadsafe(self._publish_original_subtitle(result.original_text), self._loop)

    def _on_no_match(self, details: str) -> None:
        log.warning(
            "Live track %s [t+%.1fs] KHONG NHAN DIEN DUOC gi (NoMatch) — co the do im lang keo dai,"
            " tieng on, hoac dinh dang audio sai (%s)",
            self._config.track_id, self._elapsed(), details,
        )

    def _on_synthesizing_audio(self, audio_bytes: bytes) -> None:
        """Chạy trên thread nội bộ của provider (vd Azure SDK) — chỉ được đụng vào event loop qua
        `call_soon_threadsafe`, không được `await` trực tiếp ở đây."""
        elapsed = self._elapsed()
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

    def _on_canceled(self, is_error: bool, details: str) -> None:
        """BUG THẬT (31/08/2026): trước đây chỉ log rồi để agent chạy tiếp — khi provider huỷ kết
        nối vì LỖI THẬT (vd cấu hình sai khiến server từ chối ngay), `_pump_instructor_audio` vẫn
        vô tư đẩy audio vào 1 nơi không còn ai đọc, log heartbeat "vẫn đang nhận audio" chạy đều
        khiến tưởng nhầm là đang hoạt động bình thường. Lỗi thật thì dừng hẳn agent luôn — thiết
        kế hiện tại không tự kết nối lại được."""
        if is_error:
            log.error(
                "Live track %s [t+%.1fs]: provider dich LOI THAT, dung agent - %s",
                self._config.track_id, self._elapsed(), details,
            )
            self.stop()
        else:
            log.info(
                "Live track %s [t+%.1fs]: provider dich ket thuc binh thuong (%s)",
                self._config.track_id, self._elapsed(), details,
            )

    async def _publish_translation_subtitle(self, translated_text: str) -> None:
        """Phát phụ đề DỊCH qua Data Message — không đi qua `_pcm_queue` vì đây là dữ liệu NHẸ (vài
        trăm byte text), không tranh chấp tài nguyên với audio nên không cần xếp hàng tuần tự như
        `capture_frame()`.

        F11.5 mở rộng: khi provider KHÔNG tự cho phụ đề gốc đồng bộ (Azure), CHỈ gửi phần dịch —
        phụ đề GỐC lúc đó có luồng riêng đáng tin cậy hơn (`transcription_agent.py`, chạy nhận
        diện thuần không qua bước dịch nên nhanh và ổn định hơn). `kind` phân biệt rõ cho FE.
        """
        payload = json.dumps({
            "kind": "translation",
            "targetLanguage": self._config.target_language,
            "text": translated_text,
        })
        try:
            await self._room.local_participant.publish_data(payload, reliable=True, topic=_SUBTITLE_TOPIC)
        except Exception:
            log.exception("Live track %s [t+%.1fs]: loi phat phu de dich", self._config.track_id, self._elapsed())

    async def _publish_original_subtitle(self, original_text: str) -> None:
        """F11.7 — CHỈ gọi khi `self._provider.publishes_synced_original` (Gemini): phát phụ đề
        GỐC ngay TỪ CHÍNH phiên dịch này, gắn `sourceTrackId` để FE ưu tiên ghép đúng cặp gốc-dịch
        đồng bộ tuyệt đối khi đang xem phụ đề dịch của track này — xem `LiveOriginalSubtitle`/
        `useLiveSubtitles` phía `fe/` để biết cách ưu tiên. Khác `TranscriptionAgentSession`
        (luồng độc lập, `sourceTrackId=null`, phát cho mọi người xem không phân biệt track)."""
        payload = json.dumps({
            "kind": "original",
            "text": original_text,
            "sourceTrackId": self._config.track_id,
        })
        try:
            await self._room.local_participant.publish_data(payload, reliable=True, topic=_SUBTITLE_TOPIC)
        except Exception:
            log.exception("Live track %s [t+%.1fs]: loi phat phu de goc dong bo", self._config.track_id, self._elapsed())

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
        """BUG THẬT (31/08/2026) — provider có thể trả về NGUYÊN CỤC audio đã dịch cho cả 1
        câu/đoạn dài (thấy thật trong log: 692KB ~ 21 giây audio cho 1 đoạn giảng viên nói liên
        tục ~18 giây không ngắt) — nhưng `AudioSource` của LiveKit chỉ có hàng đợi nội bộ ~1 giây
        (`queue_size_ms` mặc định). Cắt nhỏ thành từng khung ~20ms trước khi gọi
        `capture_frame()` nhiều lần — mỗi lệnh gọi nhỏ tự chờ đúng nhịp thời gian thực theo đúng
        thiết kế của `AudioSource`, không còn 1 cục khổng lồ nào cả. CHỈ được gọi từ
        `_playback_loop` (tuần tự) — không tự ý gọi hàm này từ nơi khác.
        """
        usable_len = len(pcm_bytes) - (len(pcm_bytes) % 2)
        if usable_len == 0:
            return
        try:
            for offset in range(0, usable_len, self._capture_chunk_bytes):
                chunk = pcm_bytes[offset : offset + self._capture_chunk_bytes]
                chunk_len = len(chunk) - (len(chunk) % 2)
                if chunk_len == 0:
                    continue
                samples_per_channel = chunk_len // (2 * _NUM_CHANNELS)
                frame = rtc.AudioFrame(chunk[:chunk_len], self._output_sample_rate, _NUM_CHANNELS, samples_per_channel)
                await self._audio_source.capture_frame(frame)
        except Exception:
            # Audio dịch tới TRỄ sau khi phòng/track LiveKit đã ở trạng thái không hợp lệ nữa (vd
            # giảng viên đã rời) cũng ném lỗi tương tự — coi đây là tín hiệu "hết dùng được nữa",
            # tự dừng agent luôn thay vì tiếp tục lãng phí quota cho audio muộn.
            log.exception(
                "Live track %s [t+%.1fs]: loi publish audio da dich — tu dung agent",
                self._config.track_id, self._elapsed(),
            )
            self.stop()

    async def _teardown(self) -> None:
        cfg = self._config
        try:
            self._provider.stop()
        except Exception:
            log.exception("Live track %s: loi dung provider", cfg.track_id)
        if self._pump_task is not None:
            self._pump_task.cancel()
        if self._playback_task is not None:
            self._playback_task.cancel()
        try:
            await self._room.disconnect()
        except Exception:
            log.exception("Live track %s: loi ngat ket noi LiveKit", cfg.track_id)
        log.info(
            "Live track %s [t+%.1fs]: da dung Translation Agent, giai phong tai nguyen (nhan tong %d frame)",
            cfg.track_id, self._elapsed(), self._frames_received,
        )
