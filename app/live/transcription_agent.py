"""F11.5 mở rộng (UC51) — Transcription Agent: nhận diện giọng nói GỐC của giảng viên, KHÔNG dịch,
KHÔNG tổng hợp giọng — chỉ để có phụ đề gốc "chạy chữ" độc lập với lồng tiếng.

Trước đây phụ đề gốc chỉ là sản phẩm phụ của `translation_agent.py` — không ai kích hoạt lồng
tiếng ngôn ngữ nào thì không có phiên nhận diện nào chạy, không có chữ gốc để hiện. Agent này tách
riêng: chỉ nhận diện THUẦN (rẻ và nhanh hơn vì bỏ hẳn bước dịch + tổng hợp giọng), chạy 1
luồng/phiên live (không theo ngôn ngữ), bật khi có người đầu tiên tích "Phụ đề gốc"
(`LiveOriginalSubtitleService` phía `be/`), dừng khi người cuối bỏ tích.

Kiến trúc giống hệt `translation_agent.py` (dùng thẳng `livekit` rtc SDK, không qua
`livekit-agents` framework — xem docstring file đó để biết lý do) nhưng ĐƠN GIẢN HƠN nhiều: không
publish audio track nào cả (không cần AudioSource/hàng đợi phát), chỉ phát phụ đề qua Data Message.

F11.6 (01/09/2026) — phần "ai đứng sau xử lý nhận diện" (trước đây gọi thẳng Azure SDK trong file
này) đã tách ra `app/live/providers/` (interface `LiveTranscriptionProvider` + implementation
`AzureTranscriptionProvider`), cùng khuôn với `translation_agent.py` — xem docstring
`app/live/providers/base.py` để biết lý do và vòng đời 2 bước `configure()`/`begin()`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from livekit import rtc

from app.live.providers import TranscriptionResult, make_transcription_provider

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

_SAMPLE_RATE = 16000
_NUM_CHANNELS = 1
_HEARTBEAT_EVERY_N_FRAMES = 100
# Trùng `_SUBTITLE_TOPIC` bên translation_agent.py — CÙNG 1 kênh, phân biệt bằng field "kind".
_SUBTITLE_TOPIC = "lms.live-subtitle"


@dataclass(frozen=True)
class TranscriptionAgentConfig:
    session_id: int
    room_name: str
    server_url: str
    agent_token: str
    instructor_identity: str
    source_language: str


class TranscriptionAgentSession:
    """1 phiên Transcription Agent cho ĐÚNG 1 `LiveSession` — không theo ngôn ngữ đích nào cả,
    chỉ có 1 luồng/phiên live (khác `TranslationAgentSession`, có thể nhiều luồng/phiên theo
    từng ngôn ngữ)."""

    def __init__(self, config: TranscriptionAgentConfig) -> None:
        self._config = config
        self._room = rtc.Room()
        self._provider = make_transcription_provider()
        self._stop_event = asyncio.Event()
        self._loop = asyncio.get_event_loop()
        self._pump_task: asyncio.Task | None = None
        self._started_at = time.monotonic()
        self._frames_received = 0

    def _elapsed(self) -> float:
        return time.monotonic() - self._started_at

    async def run(self) -> None:
        cfg = self._config
        log.info(
            "Live session %s: bat dau Transcription Agent (ngon ngu goc %s) trong phong %s",
            cfg.session_id, cfg.source_language, cfg.room_name,
        )
        self._setup_provider()

        @self._room.on("track_subscribed")
        def _on_track_subscribed(
            track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity == cfg.instructor_identity:
                log.info(
                    "Live session %s [t+%.1fs]: da subscribe duoc audio giang vien",
                    cfg.session_id, self._elapsed(),
                )
                self._pump_task = asyncio.create_task(self._pump_instructor_audio(track))

        @self._room.on("disconnected")
        def _on_room_disconnected(reason=None) -> None:
            log.info(
                "Live session %s [t+%.1fs]: phong LiveKit bi dong tu ben ngoai (%s), tu dung agent",
                cfg.session_id, self._elapsed(), reason,
            )
            self.stop()

        try:
            await self._room.connect(cfg.server_url, cfg.agent_token)
            self._provider.begin()
            await self._stop_event.wait()
        except Exception:
            log.exception("Live session %s: Transcription Agent gap loi, dung som", cfg.session_id)
        finally:
            await self._teardown()

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._stop_event.set)

    async def _pump_instructor_audio(self, track: rtc.Track) -> None:
        stream = rtc.AudioStream.from_track(track=track, sample_rate=_SAMPLE_RATE, num_channels=_NUM_CHANNELS)
        try:
            async for event in stream:
                self._provider.write_audio(bytes(event.frame.data))
                self._frames_received += 1
                if self._frames_received % _HEARTBEAT_EVERY_N_FRAMES == 0:
                    log.debug(
                        "Live session %s [t+%.1fs]: van dang nhan audio giang vien (%d frame)",
                        self._config.session_id, self._elapsed(), self._frames_received,
                    )
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Live session %s: loi doc audio giang vien", self._config.session_id)
        finally:
            await stream.aclose()

    def _setup_provider(self) -> None:
        cfg = self._config
        self._provider.configure(
            source_language=cfg.source_language,
            on_recognizing=self._on_recognizing,
            on_recognized=self._on_recognized,
            on_no_match=self._on_no_match,
            on_canceled=self._on_canceled,
            on_session_started=lambda: log.debug(
                "Live session %s [t+%.1fs]: provider session_started", cfg.session_id, self._elapsed(),
            ),
        )

    def _on_recognizing(self, result: TranscriptionResult) -> None:
        """Kết quả TẠM — "chạy chữ" kiểu phụ đề YouTube live. Xem ghi chú tương tự ở
        `translation_agent.py::_on_recognizing`."""
        log.debug(
            "Live session %s [t+%.1fs] dang nhan dien (tam): '%s'",
            self._config.session_id, self._elapsed(), result.text,
        )
        asyncio.run_coroutine_threadsafe(self._publish_subtitle(result.text), self._loop)

    def _on_recognized(self, result: TranscriptionResult) -> None:
        """Kết quả CHỐT — thường chỉ sửa nhẹ chính tả/dấu câu so với bản tạm gần nhất."""
        log.info(
            "Live session %s [t+%.1fs] DA CHOT CAU GOC (provider=%s): '%s'",
            self._config.session_id, self._elapsed(), type(self._provider).__name__, result.text,
        )
        asyncio.run_coroutine_threadsafe(self._publish_subtitle(result.text), self._loop)

    def _on_no_match(self) -> None:
        log.warning(
            "Live session %s [t+%.1fs] KHONG NHAN DIEN DUOC gi (NoMatch)",
            self._config.session_id, self._elapsed(),
        )

    def _on_canceled(self, is_error: bool, details: str) -> None:
        if is_error:
            log.error(
                "Live session %s [t+%.1fs]: provider nhan dien LOI THAT, dung agent - %s",
                self._config.session_id, self._elapsed(), details,
            )
            self.stop()
        else:
            log.info(
                "Live session %s [t+%.1fs]: provider nhan dien ket thuc binh thuong (%s)",
                self._config.session_id, self._elapsed(), details,
            )

    async def _publish_subtitle(self, text: str) -> None:
        # F11.7 — `sourceTrackId=None` tường minh: đây LUÔN là luồng gốc ĐỘC LẬP (không gắn track
        # dịch nào), phát cho MỌI người xem bất kể đang xem phụ đề dịch ngôn ngữ nào — khác phụ đề
        # gốc ĐỒNG BỘ theo track cụ thể mà `GeminiTranslationProvider` tự phát (xem
        # `translation_agent.py::_publish_original_subtitle`). FE ưu tiên đúng `sourceTrackId` của
        # track đang xem khi có, rơi về luồng này (`sourceTrackId=null`) khi không có track nào
        # đang xem hoặc provider đang dùng không phải Gemini.
        payload = json.dumps({"kind": "original", "text": text, "sourceTrackId": None})
        try:
            await self._room.local_participant.publish_data(payload, reliable=True, topic=_SUBTITLE_TOPIC)
        except Exception:
            log.exception("Live session %s [t+%.1fs]: loi phat phu de goc", self._config.session_id, self._elapsed())

    async def _teardown(self) -> None:
        cfg = self._config
        try:
            self._provider.stop()
        except Exception:
            log.exception("Live session %s: loi dung provider", cfg.session_id)
        if self._pump_task is not None:
            self._pump_task.cancel()
        try:
            await self._room.disconnect()
        except Exception:
            log.exception("Live session %s: loi ngat ket noi LiveKit", cfg.session_id)
        log.info(
            "Live session %s [t+%.1fs]: da dung Transcription Agent (nhan tong %d frame)",
            cfg.session_id, self._elapsed(), self._frames_received,
        )
