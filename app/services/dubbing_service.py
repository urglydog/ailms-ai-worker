"""UC19 — điều phối toàn bộ pipeline lồng tiếng cho một cặp (bài học, ngôn ngữ).

Viết lại thuật toán từ `core/` (VideoLingo) theo THAM SỐ TƯỜNG MINH thay vì gọi
thẳng — `core/` đọc `config.yaml` toàn cục và ghi đường dẫn cố định nên KHÔNG chạy
song song nhiều job được (xem `doc/DEVELOPMENT_PLAN.md` mục 1, cảnh báo cuối bảng).
Mọi tham số (đường dẫn tạm, job_id, ngôn ngữ...) ở đây đều truyền qua đối số hàm.

Luồng đầy đủ khớp `lms-dubbing-pipeline`:
  ⑧ kiểm nguồn video còn khả dụng (BR-DUB-11)
  ⑨ tách audio gốc
  ⑩ chia phân đoạn cố định 10 phút (BR-CHUNK-02)
  ⑪ ASR từng chunk — BỎ QUA nếu bài học đã có transcript gốc từ job trước (BR-DUB-01)
  ⑫ dịch Gemini theo batch cả chunk (BR-DUB-02, xem `services/translation.py`)
  ⑬ Adaptive Speech Rate cho từng câu (BR-DUB-03)
  ⑭ Edge-TTS -> ghép thành 1 file/chunk
  ⑮ chunk xong -> publish tiến độ NGAY (BR-CHUNK-03)
  ⑯ mọi chunk COMPLETED -> ghép `final.mp3` (BR-CHUNK-05)
  ⑰ dọn file trung gian (BR-STORAGE-01)
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app import audio_utils, media, redis_client, source_audio, storage
from app import usage as usage_mod
from app.config import settings
from app.http import backend_client
from app.models import Segment
from app.providers import azure_tts, groq_asr
from app.services import background_music, translation, tutor_indexing
from app.storage import upload_file

source_audio_mod = source_audio   # trong _process_chunk_* tên `source_audio` là tham số đường dẫn

log = logging.getLogger(__name__)

MIN_SPEECH_RATIO = 0.10          # BR-DUB-10
R_UPPER_BOUND = Decimal("1.3")   # BR-DUB-03
R_LOWER_BOUND = Decimal("1.0")
MAX_TTS_RATE = "+30%"            # Mức tối đa của nhánh BR-DUB-03 khi hết lượt re-summarize
_MAX_TEMPO = Decimal("1.3")       # cùng mức +30%, áp bằng FFmpeg atempo thay vì gọi lại TTS


class SkippedPipelineError(Exception):
    """BR-DUB-10 — ký âm rỗng hoặc thoại < 10% thời lượng. TUYỆT ĐỐI không retry."""


# BR-DUB-11 — định nghĩa ở `app/source_audio.py` (dùng chung với bước tải audio gốc khi cần).
SourceUnavailableError = source_audio.SourceUnavailableError


@dataclass(frozen=True)
class ChunkPlan:
    index: int
    start_sec: int
    end_sec: int


def split_into_chunks(duration_sec: int, chunk_minutes: int) -> list[ChunkPlan]:
    """BR-CHUNK-02 — phân đoạn CỐ ĐỊNH N phút, phân đoạn cuối chứa phần dư."""
    if duration_sec <= 0:
        return [ChunkPlan(0, 0, 0)]
    chunk_len_sec = chunk_minutes * 60
    chunks: list[ChunkPlan] = []
    start = 0
    index = 0
    while start < duration_sec:
        end = min(start + chunk_len_sec, duration_sec)
        chunks.append(ChunkPlan(index, start, end))
        start = end
        index += 1
    return chunks


MIN_SEGMENT_SEC = 0.05


def clamp_stt_segments(stt_segments, audio_len_sec: float) -> list[tuple[float, float, str]]:
    """Kẹp mốc (tương đối trong chunk) của từng câu ASR vào [0, audio_len_sec].
    Bỏ câu rỗng, câu bắt đầu từ cuối audio trở đi, hoặc còn dài < MIN_SEGMENT_SEC sau khi kẹp."""
    out: list[tuple[float, float, str]] = []
    for s in stt_segments:
        text = (s.text or "").strip()
        start = max(0.0, float(s.start))
        end = min(float(s.end), audio_len_sec)
        if not text or start >= audio_len_sec or end - start < MIN_SEGMENT_SEC:
            continue
        out.append((start, end, s.text))
    return out


@usage_mod.tagged("DUBBING_TRANSCRIBE")
async def run_dubbing_pipeline(
    job_id: int, lesson_id: int, video_url: str, target_language: str, celery_task_id: str | None = None,
) -> dict:
    """Điểm vào duy nhất — gọi từ `app/tasks/dubbing.py::run_pipeline` qua `asyncio.run`."""
    work_dir = Path(settings.temp_dir) / f"job_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    music_task: asyncio.Task | None = None

    try:
        ctx = await backend_client.get_context(job_id)
        # F5.3 mở rộng — sự kiện "stage" chỉ để FE hiển thị nhãn cụ thể hơn (không phải chunk
        # xong hay job xong), KHÔNG có tác dụng gì tới logic pipeline nếu publish thất bại.
        await redis_client.publish_progress(job_id, lesson_id, stage="PREPARING")
        # Điểm 4 (22/11/2026): đánh thức GPU tách nhạc NGAY bây giờ để nó khởi động song song với việc
        # tải audio gốc (không chờ). Bài đã có nhạc trên B2 thì không đánh thức.
        background_music.warm_up(lesson_id, ctx.video_url, ctx.duration_sec)

        source_path = work_dir / "source.wav"

        async def _download(path: Path) -> None:
            if ctx.video_source == "YOUTUBE":
                await media.download_youtube_audio(ctx.video_url, path)
            else:
                await media.extract_audio_from_url(ctx.video_url, path)

        source_audio.register(source_path, _download)
        # Tối ưu B (22/11/2026): bài đã có bản ký âm + biết thời lượng + nhạc nền (nếu bật) đã có trên B2
        # -> KHÔNG tải audio gốc trước; chỉ tải nếu một bước thật sự cần (xem `app/source_audio.py`).
        if not await _can_defer_source(ctx, lesson_id):
            await source_audio.ensure(source_path)
        else:
            log.info("Job %s: da co ban ky am + nhac nen, chua tai audio goc (chi tai khi can)", job_id)

        duration_sec = ctx.duration_sec or int(
            await media.probe_duration_sec(await source_audio.ensure(source_path))
        )
        chunks = split_into_chunks(duration_sec, settings.chunk_minutes)
        await backend_client.start_job(job_id, total_chunks=len(chunks), celery_task_id=celery_task_id)

        # M2: tách nhạc nền chạy NỀN song song với các chunk (None nếu tắt BGM_SEPARATION).
        music_task = background_music.start_separation(source_path, work_dir, lesson_id, ctx.video_url)
        reuse_source = ctx.source_transcript_available
        next_seq = 1
        chunk_audio_paths: list[Path] = []
        fallback_count = 0

        # Dây chuyền 2 công đoạn (22/11/2026, bài > 10 phút):
        #   A = nhận dạng + dịch (Groq, Gemini)      B = TTS, ghép, trộn nhạc, upload, báo backend (Azure, B2)
        # A của chunk k+1 chạy CÙNG LÚC với B của chunk k. Mỗi công đoạn vẫn chạy lần lượt theo thứ tự
        # chunk -> backend nhận kết quả đúng thứ tự, từng cái một (`upsertChunk` không chịu được 2 lần
        # báo đồng thời), và số thứ tự câu của chunk k+1 tính từ số câu ASR của chunk k như cũ.
        prefetch: asyncio.Task | None = None

        def _start_prepare(chunk: ChunkPlan, seq: int) -> asyncio.Task:
            return asyncio.create_task(_prepare_chunk_with_retry(
                job_id, lesson_id, ctx, chunk, len(chunks), source_path, work_dir, reuse_source, seq,
            ))

        for idx, chunk in enumerate(chunks):
            try:
                task, prefetch = (prefetch or _start_prepare(chunk, next_seq)), None
                prepared = await task
                next_seq += prepared.consumed
                if idx + 1 < len(chunks):
                    prefetch = _start_prepare(chunks[idx + 1], next_seq)   # chạy trong lúc chunk này làm B
                chunk_audio, _consumed = await _finish_chunk_with_retry(
                    prepared, job_id, lesson_id, ctx, chunk, len(chunks), source_path, work_dir, music_task,
                )
                chunk_audio_paths.append(chunk_audio)
                await redis_client.publish_progress(
                    job_id, lesson_id, chunkIndex=chunk.index, totalChunks=len(chunks), status="COMPLETED",
                )
            except SkippedPipelineError:
                if prefetch is not None:
                    prefetch.cancel()
                raise
            except Exception as exc:
                # BR-CHUNK-04: hết retry cho MỘT chunk — giữ audio GỐC riêng đoạn đó,
                # các chunk khác vẫn phát bản lồng tiếng bình thường.
                log.error("Chunk %s cua job %s that bai sau %s lan retry: %s", chunk.index, job_id, settings.max_retry, exc)
                fallback_count += 1
                fallback_audio = work_dir / f"chunk_{chunk.index}_original.mp3"
                await audio_utils.extract_range(
                    await source_audio.ensure(source_path), chunk.start_sec, chunk.end_sec, fallback_audio,
                )
                chunk_audio_paths.append(fallback_audio)
                await backend_client.upsert_chunk_failed(
                    job_id, chunk.index, start_sec=chunk.start_sec, end_sec=chunk.end_sec, error_message=str(exc),
                )
                await redis_client.publish_progress(
                    job_id, lesson_id, chunkIndex=chunk.index, totalChunks=len(chunks), status="FAILED",
                )

        if chunks and fallback_count == len(chunks):
            # Không một chunk nào lồng tiếng được thật — final.mp3 sẽ chỉ là audio gốc ghép
            # lại, không khác gì "Xem tạm với âm thanh gốc" mà FE đã có sẵn. Báo FAILED thay
            # vì COMPLETED để không đánh lừa là đã có bản dịch, tránh việc AiJob.status thành
            # công giả trong khi transcripts/audio_chunks không có dòng nào (0 hàng thật).
            error_message = (
                f"Toan bo {len(chunks)}/{len(chunks)} doan long tieng that bai sau "
                f"{settings.max_retry} lan retry moi doan — hoc vien van xem duoc video voi "
                f"am thanh goc, chua co ban dich thuc su."
            )
            log.error("Job %s: %s", job_id, error_message)
            await backend_client.finish_failed(job_id, error_message=error_message)
            await redis_client.publish_progress(job_id, lesson_id, status="FAILED")
            return {"status": "FAILED", "jobId": job_id, "reason": "ALL_CHUNKS_FALLBACK"}

        await redis_client.publish_progress(job_id, lesson_id, stage="FINALIZING")
        t_final = time.monotonic()
        if len(chunks) == 1 and fallback_count == 0:
            # Điểm 2 (22/11/2026): bài 1 chunk -> final.mp3 giống hệt file chunk vừa upload. Dùng luôn
            # file + URL đó, bỏ giải mã/mã hoá lại và upload lần 2 (trước ~12–25 s/bài).
            final_path = chunk_audio_paths[0]
            final_url = storage.public_url(_chunk_key(ctx, chunks[0]))
        else:
            final_path = work_dir / "final.mp3"
            await audio_utils.concat_files(chunk_audio_paths, final_path)
            final_url = await upload_file(final_path, f"dubbing/{lesson_id}/{target_language}/final.mp3")
        # độ dài đọc từ header (không giải mã cả bài) — chỉ cần số giây nguyên cho AudioTrack
        final_duration = (await audio_utils.probe_audio(final_path))[0]
        final_size = final_path.stat().st_size
        log.info("TIMING job=%s final=%.1fs (%s chunk)", job_id, time.monotonic() - t_final, len(chunks))

        await backend_client.finish_completed(
            job_id, final_url=final_url, duration_sec=int(final_duration), file_size=final_size,
        )
        # F5.3: sự kiện CẤP-JOB (không có chunkIndex) — FE phân biệt với sự kiện cấp-chunk để
        # biết CHÍNH XÁC lúc nào dừng progress bar (chunk cuối "COMPLETED" chưa có nghĩa là job
        # đã xong: còn phải chờ FFmpeg concat + upload B2 + gọi finish_completed ở trên).
        await redis_client.publish_progress(job_id, lesson_id, status="COMPLETED")
        return {"status": "COMPLETED", "jobId": job_id}

    except SkippedPipelineError as exc:
        await backend_client.finish_skipped(job_id, reason=str(exc))
        await redis_client.publish_progress(job_id, lesson_id, status="SKIPPED")
        return {"status": "SKIPPED", "jobId": job_id}
    except SourceUnavailableError as exc:
        await backend_client.finish_source_unavailable(job_id, error_message=str(exc))
        await redis_client.publish_progress(job_id, lesson_id, status="FAILED")
        return {"status": "FAILED", "jobId": job_id, "reason": "SOURCE_UNAVAILABLE"}
    except Exception as exc:
        log.exception("Pipeline long tieng that bai cho job %s", job_id)
        await backend_client.finish_failed(job_id, error_message=str(exc))
        await redis_client.publish_progress(job_id, lesson_id, status="FAILED")
        raise
    finally:
        for pending in list(_prepare_tasks):
            pending.cancel()
        if music_task is not None and not music_task.done():
            music_task.cancel()  # job dừng sớm (lỗi/skip) thì không chờ Modal nữa
        await background_music.wait_pending_uploads()  # lưu cache nhạc lên B2 phải xong trước khi xoá file
        await _wait_background_indexing()             # tối ưu C: index Gia sư AI chạy nền phải xong
        source_audio.unregister(work_dir / "source.wav")
        # BR-STORAGE-01: dọn ngay sau job — cleanup_temp_files() (Celery beat) chỉ là
        # lưới an toàn cho thư mục mồ côi khi worker crash giữa chừng.
        shutil.rmtree(work_dir, ignore_errors=True)


async def _can_defer_source(ctx, lesson_id: int) -> bool:
    """Có thể bỏ qua việc tải audio gốc lúc đầu job không (tối ưu B)?

    Cần đủ 3 điều kiện: đã có bản ký âm gốc (không chạy ASR), backend đã biết thời lượng bài (không
    phải đo từ file), và nhạc nền tắt hoặc đã được tách sẵn trên B2 (không phải gửi audio đi tách).
    """
    if not ctx.source_transcript_available or not ctx.duration_sec:
        return False
    if settings.bgm_separation != "modal":
        return True
    prefix = background_music.cache_prefix(lesson_id, ctx.video_url)
    return bool(prefix) and await storage.exists(f"{prefix}/music.mp3") and await storage.exists(f"{prefix}/vocals.mp3")


_indexing_tasks: set[asyncio.Task] = set()


async def _index_for_tutor(lesson_id: int, language: str | None, segments: list[Segment]) -> None:
    t0 = time.monotonic()
    try:
        await tutor_indexing.index_segments(lesson_id, language, segments)
        log.info("Index Gia su AI cho lesson %s xong (chay nen): %.1fs", lesson_id, time.monotonic() - t0)
    except Exception as exc:
        log.warning("Danh index embedding cho lesson %s that bai (khong anh huong job long tieng): %s", lesson_id, exc)


async def _wait_background_indexing(timeout_sec: float = 300) -> None:
    if _indexing_tasks:
        await asyncio.wait(list(_indexing_tasks), timeout=timeout_sec)


_prepare_tasks: set[asyncio.Task] = set()


async def _with_retry(label: str, job_id: int, chunk: ChunkPlan, step):
    """BR-CHUNK-04 cho 1 công đoạn: thử tối đa `MAX_RETRY` lần, chờ 2^lần giây. SKIPPED không thử lại."""
    last_error: Exception | None = None
    for attempt in range(1, settings.max_retry + 1):
        try:
            return await step()
        except SkippedPipelineError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt == settings.max_retry:
                break
            wait_sec = 2**attempt
            log.warning(
                "Chunk %s job %s loi o %s (lan %s/%s): %s — retry sau %ss",
                chunk.index, job_id, label, attempt, settings.max_retry, exc, wait_sec,
            )
            await asyncio.sleep(wait_sec)
    assert last_error is not None
    raise last_error


async def _prepare_chunk_with_retry(
    job_id: int, lesson_id: int, ctx, chunk: ChunkPlan, total_chunks: int,
    source_audio: Path, work_dir: Path, reuse_source: bool, next_seq: int,
) -> "PreparedChunk":
    task = asyncio.current_task()
    if task is not None:
        _prepare_tasks.add(task)
        task.add_done_callback(_prepare_tasks.discard)
    return await _with_retry("nhan dang/dich", job_id, chunk, lambda: _prepare_chunk(
        job_id, lesson_id, ctx, chunk, total_chunks, source_audio, work_dir, reuse_source, next_seq,
    ))


async def _finish_chunk_with_retry(
    prepared: "PreparedChunk", job_id: int, lesson_id: int, ctx, chunk: ChunkPlan, total_chunks: int,
    source_audio: Path, work_dir: Path, music_task: asyncio.Task | None = None,
) -> tuple[Path, int]:
    # Thử lại CHỈ công đoạn B, dùng lại kết quả ASR/dịch của A: không chạy lại Whisper nên số câu
    # (và số thứ tự câu của chunk sau, đã được tính) không đổi giữa các lần thử.
    return await _with_retry("tts/ghep/upload", job_id, chunk, lambda: _finish_chunk(
        prepared, job_id, lesson_id, ctx, chunk, total_chunks, source_audio, work_dir, music_task,
    ))


async def _process_chunk_with_retry(
    job_id: int, lesson_id: int, ctx, chunk: ChunkPlan, total_chunks: int,
    source_audio: Path, work_dir: Path, reuse_source: bool, next_seq: int,
    music_task: asyncio.Task | None = None,
) -> tuple[Path, int]:
    """BR-CHUNK-04 — retry tối đa `MAX_RETRY` lần, exponential backoff. `SKIPPED`
    (raise `SkippedPipelineError`) KHÔNG được retry — phải bubble lên ngay.
    """
    last_error: Exception | None = None
    for attempt in range(1, settings.max_retry + 1):
        try:
            return await _process_chunk_once(
                job_id, lesson_id, ctx, chunk, total_chunks, source_audio, work_dir, reuse_source, next_seq,
                music_task,
            )
        except SkippedPipelineError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt == settings.max_retry:
                break
            wait_sec = 2**attempt
            log.warning(
                "Chunk %s job %s loi (lan %s/%s): %s — retry sau %ss",
                chunk.index, job_id, attempt, settings.max_retry, exc, wait_sec,
            )
            await asyncio.sleep(wait_sec)
    assert last_error is not None
    raise last_error


@dataclass
class PreparedChunk:
    """Kết quả công đoạn A (nhận dạng + dịch) của 1 chunk, dùng cho công đoạn B."""

    segments: list[Segment]
    translated_texts: list[str]
    detected_language: str | None
    generate_source_dtos: bool
    t_start: float
    t_asr: float
    t_translated: float

    @property
    def consumed(self) -> int:
        """Số `seq` chunk này dùng — chunk sau đánh số tiếp từ đây (chỉ khi vừa chạy ASR)."""
        return len(self.segments) if self.generate_source_dtos else 0


async def _process_chunk_once(
    job_id: int, lesson_id: int, ctx, chunk: ChunkPlan, total_chunks: int,
    source_audio: Path, work_dir: Path, reuse_source: bool, next_seq: int,
    music_task: asyncio.Task | None = None,
) -> tuple[Path, int]:
    """Cả 2 công đoạn của 1 chunk, nối tiếp (giữ cho script NCKH và test)."""
    prepared = await _prepare_chunk(
        job_id, lesson_id, ctx, chunk, total_chunks, source_audio, work_dir, reuse_source, next_seq,
    )
    return await _finish_chunk(prepared, job_id, lesson_id, ctx, chunk, total_chunks, source_audio, work_dir, music_task)


async def _prepare_chunk(
    job_id: int, lesson_id: int, ctx, chunk: ChunkPlan, total_chunks: int,
    source_audio: Path, work_dir: Path, reuse_source: bool, next_seq: int,
) -> PreparedChunk:
    """Công đoạn A: lấy câu (ASR hoặc bản ký âm có sẵn) và bản dịch."""
    t_start = time.monotonic()
    detected_language: str | None = None
    generate_source_dtos = False

    if reuse_source:
        segments = [
            # kẹp `end` vào biên chunk: transcript cũ (lưu trước bản sửa 11/11) có thể có mốc vượt audio
            Segment(seq=s.seq, start=float(s.start_sec), end=min(float(s.end_sec), float(chunk.end_sec)), text=s.text)
            for s in ctx.source_segments
            if chunk.start_sec <= float(s.start_sec) < chunk.end_sec
        ]
    else:
        await redis_client.publish_progress(
            job_id, lesson_id, stage="ASR", chunkIndex=chunk.index, totalChunks=total_chunks,
        )
        chunk_wav = work_dir / f"chunk_{chunk.index}_src.wav"
        await audio_utils.extract_range(
            await source_audio_mod.ensure(source_audio), chunk.start_sec, chunk.end_sec, chunk_wav,
        )
        stt = await groq_asr.transcribe(str(chunk_wav))

        chunk_len = chunk.end_sec - chunk.start_sec
        if chunk_len <= 0 or (stt.speech_duration_sec / chunk_len) < MIN_SPEECH_RATIO:
            raise SkippedPipelineError(
                f"Chunk {chunk.index}: ty le loi thoai qua thap "
                f"({stt.speech_duration_sec:.1f}s / {chunk_len}s) — BR-DUB-10"
            )
        detected_language = stt.language
        generate_source_dtos = True
        # Whisper đôi khi trả mốc VƯỢT QUÁ độ dài audio (đo được: câu cuối "Thank you."
        # 709,4 → 739,4 s trong khi audio dài 718 s) → kẹp mốc vào [0, độ dài thật của chunk],
        # bỏ câu nằm hẳn ngoài audio, để không đệm lặng thừa cuối bài.
        audio_len = min(float(chunk_len), stt.duration_sec) if stt.duration_sec > 0 else float(chunk_len)
        segments = []
        for s in clamp_stt_segments(stt.segments, audio_len):
            segments.append(Segment(
                seq=next_seq + len(segments), start=chunk.start_sec + s[0], end=chunk.start_sec + s[1], text=s[2],
            ))

    if not segments:
        t_now = time.monotonic()
        return PreparedChunk([], [], None, False, t_start, t_now, t_now)

    t_asr = time.monotonic()
    if ctx.target_transcript_available:
        # Bản dịch ngôn ngữ đích đã có sẵn (thường do UC24/25 sinh học liệu tạo trước khi ai bấm
        # lồng tiếng) — bỏ qua HẲN bước dịch Gemini (BR-DUB-02), tiết kiệm 2 lượt gọi/chunk.
        # `seq` khớp 1-1 với `segments` (cùng nguồn source_segments đã dịch nguyên vẹn câu-theo-câu).
        target_by_seq = {s.seq: s.text for s in ctx.target_segments}
        translated_texts = [target_by_seq.get(seg.seq, "") for seg in segments]
    else:
        await redis_client.publish_progress(
            job_id, lesson_id, stage="TRANSLATE", chunkIndex=chunk.index, totalChunks=total_chunks,
        )
        # Chunk chạy lại (BR-CHUNK-04) dùng lại bản dịch lần trước — không trả tiền dịch 2 lần.
        cache_file = work_dir / f"chunk_{chunk.index}_translated.json"
        translated_texts = _read_json_list(cache_file, len(segments))
        if translated_texts is None:
            cps = await _voice_chars_per_sec(ctx.voice_name)
            max_chars = [max(4, int(cps * seg.duration * _TARGET_R)) for seg in segments] if cps else None
            translated_texts = await translation.translate_batch(
                segments, ctx.source_language or detected_language or "unknown", ctx.target_language,
                max_chars=max_chars,
            )
            cache_file.write_text(json.dumps(translated_texts, ensure_ascii=False), encoding="utf-8")

    return PreparedChunk(
        segments, translated_texts, detected_language, generate_source_dtos, t_start, t_asr, time.monotonic(),
    )


async def _finish_chunk(
    prepared: PreparedChunk, job_id: int, lesson_id: int, ctx, chunk: ChunkPlan, total_chunks: int,
    source_audio: Path, work_dir: Path, music_task: asyncio.Task | None = None,
) -> tuple[Path, int]:
    """Công đoạn B: TTS, ghép theo mốc, trộn nhạc nền, upload, báo backend."""
    segments, translated_texts = prepared.segments, prepared.translated_texts
    detected_language, generate_source_dtos = prepared.detected_language, prepared.generate_source_dtos
    t_start, t_asr, t_translated = prepared.t_start, prepared.t_asr, prepared.t_translated
    t_b = time.monotonic()

    if not segments:
        # Đoạn toàn khoảng lặng (hay gặp khi tái sử dụng transcript, chunk rơi đúng
        # vào quãng nghỉ) — giữ nguyên audio gốc cho đoạn này, không gọi AI.
        empty_audio = work_dir / f"chunk_{chunk.index}_dub.mp3"
        await audio_utils.extract_range(
            await source_audio_mod.ensure(source_audio), chunk.start_sec, chunk.end_sec, empty_audio,
        )
        audio_url = await _upload_chunk_audio(empty_audio, ctx, chunk)
        await backend_client.upsert_chunk_completed(
            job_id, chunk.index, start_sec=chunk.start_sec, end_sec=chunk.end_sec, audio_file_url=audio_url,
            detected_source_language=None, source_segments=None, target_segments=[],
        )
        return empty_audio, 0

    await redis_client.publish_progress(
        job_id, lesson_id, stage="TTS", chunkIndex=chunk.index, totalChunks=total_chunks,
    )
    sentence_paths = [work_dir / f"chunk_{chunk.index}_seg_{seg.seq}.mp3" for seg in segments]
    # mốc gốc của câu, tính TƯƠNG ĐỐI từ đầu chunk
    desired_onsets = [max(0.0, seg.start - chunk.start_sec) for seg in segments]
    target_dtos: list[dict] = []
    source_dtos: list[dict] | None = [] if generate_source_dtos else None

    synthesized = await _synthesize_segments(
        segments, translated_texts, ctx.voice_name, sentence_paths, ctx.target_language,
    )
    t_tts = time.monotonic()
    t_wait = t_b - t_translated   # thời gian A xong sớm, chờ chunk trước làm xong B (dây chuyền)

    for seg, (result, final_text, was_summarized) in zip(segments, synthesized):
        target_dtos.append(backend_client.segment_to_json(
            seg.seq, Decimal(str(seg.start)), Decimal(str(seg.end)), final_text,
            speech_rate=result.applied_rate, was_summarized=was_summarized,
        ))
        if generate_source_dtos:
            source_dtos.append(backend_client.segment_to_json(
                seg.seq, Decimal(str(seg.start)), Decimal(str(seg.end)), seg.text,
            ))

    if generate_source_dtos and source_dtos:
        # Việc phát sinh của F8.1 (Socratic Tutor, UC30): đánh index embedding CÂU GỐC
        # (chưa dịch) lên Supabase Vector để RAG truy xuất sau này. Chỉ chạy đúng 1 lần
        # cho lần đầu bài học được lồng tiếng (generate_source_dtos chỉ True khi
        # reuse_source=False) — các job dịch sang ngôn ngữ khác sau đó không lặp lại.
        # Lỗi ở bước này KHÔNG được làm hỏng cả job lồng tiếng (BR-TUTOR-03 là tính năng
        # phụ trợ, không phải luồng chính) nên bọc try/except riêng, chỉ log cảnh báo.
        # Tối ưu C (22/11/2026): chạy NỀN — người học không cần chờ bước này mới nghe được bản lồng
        # tiếng (trước nằm trong `ghep`, ~3–5 s). Job đợi nó xong trước khi kết thúc (`finally`).
        task = asyncio.create_task(_index_for_tutor(ctx.lesson_id, detected_language, list(segments)))
        _indexing_tasks.add(task)
        task.add_done_callback(_indexing_tasks.discard)

    await redis_client.publish_progress(
        job_id, lesson_id, stage="UPLOADING", chunkIndex=chunk.index, totalChunks=total_chunks,
    )
    chunk_audio = work_dir / f"chunk_{chunk.index}_dub.mp3"
    # BR-CHUNK-05 (sửa 11/11/2026): xếp câu theo mốc tuyệt đối thay vì chèn khoảng lặng
    # cố định `start_i − end_{i-1}` — cách cũ làm câu tràn đẩy lùi mọi câu sau, trễ cộng dồn
    # (đo được +96 s ở bài 15 phút). Chunk luôn được khớp đúng độ dài để không lan sang chunk sau.
    timeline = await audio_utils.place_on_timeline(
        sentence_paths, desired_onsets, float(chunk.end_sec - chunk.start_sec), chunk_audio,
        durations_sec=[result.duration_sec for result, _text, _summarized in synthesized],
    )
    if timeline.tempo_applied > 1.0 or timeline.max_delay_sec > 2.0:
        log.info(
            "Chunk %s job %s: tre toi da %.1fs, dai tho %.1fs -> tang toc ca doan x%.3f",
            chunk.index, job_id, timeline.max_delay_sec, timeline.raw_length_sec, timeline.tempo_applied,
        )
    if timeline.raw_length_sec / max(timeline.tempo_applied, 1.0) > (chunk.end_sec - chunk.start_sec) + 0.5:
        log.warning(
            "Chunk %s job %s: van du %.1fs sau khi tang toc toi da x%s — phan cuoi bi cat",
            chunk.index, job_id,
            timeline.raw_length_sec / timeline.tempo_applied - (chunk.end_sec - chunk.start_sec),
            audio_utils.MAX_CHUNK_TEMPO,
        )

    t_timeline = time.monotonic()
    await background_music.mix_into_chunk(chunk_audio, music_task, chunk.start_sec, chunk.end_sec, work_dir)
    t_music = time.monotonic()
    audio_url = await _upload_chunk_audio(chunk_audio, ctx, chunk)
    await backend_client.upsert_chunk_completed(
        job_id, chunk.index, start_sec=chunk.start_sec, end_sec=chunk.end_sec, audio_file_url=audio_url,
        detected_source_language=detected_language, source_segments=source_dtos, target_segments=target_dtos,
    )
    t_end = time.monotonic()
    # Hiệu năng dubbing (bước 0): thời gian từng bước của chunk — để biết thời gian thật sự đi đâu.
    log.info(
        "TIMING job=%s chunk=%s cau=%s asr=%.1fs dich=%.1fs cho_chunk_truoc=%.1fs tts=%.1fs ghep=%.1fs nhac=%.1fs "
        "upload=%.1fs tong=%.1fs",
        job_id, chunk.index, len(segments), t_asr - t_start, t_translated - t_asr, t_wait, t_tts - t_b,
        t_timeline - t_tts, t_music - t_timeline, t_end - t_music, t_end - t_start,
    )

    return chunk_audio, len(segments) if generate_source_dtos else 0


async def _synthesize_segments(
    segments: list[Segment], texts: list[str], voice_name: str, out_paths: list[Path], target_language: str,
) -> list[tuple[azure_tts.SynthesisResult, str, bool]]:
    """BR-DUB-03 (Adaptive Speech Rate) cho CẢ chunk — viết lại cho tốc độ và chi phí (15/11/2026).

    Trước đây mỗi câu chạy tuần tự và gọi TTS trung bình 2,7 lần (đo NCKH: 2.097 lần/787 câu):
    1 lần đo, 1 lần sau mỗi lần rút gọn, thêm 1 lần CHỈ để đổi `rate`; rút gọn gọi Gemini từng câu.
    Giờ:
      1. Tổng hợp mọi câu SONG SONG (`tts_concurrency`, S1).
      2. Câu có R > 1.3 (và khung ≥ `min_resummarize_frame_sec`): rút gọn CẢ LÔ trong 1 lời gọi
         Gemini (S4), tổng hợp lại song song; lặp tối đa `max_resummarize_attempts` vòng.
      3. Câu còn R > 1.0: tăng tốc bằng FFmpeg `atempo` trên file có sẵn, trần ×1.3 (S2) — không
         gọi lại TTS. Câu R ≤ 1.0 giữ nguyên (khoảng lặng do `place_on_timeline` dựng).
    R = T_exp / T_orig (xem `_speech_rate`; chiều đã đảo so với văn bản BR gốc, giữ 3 mốc 1.0/1.3).
    """
    n = len(segments)
    if n == 0:
        return []
    tts_sem = asyncio.Semaphore(max(1, settings.tts_concurrency))

    async def tts(i: int) -> azure_tts.SynthesisResult:
        # Chunk chạy lại: câu đã có file giọng hợp lệ cho ĐÚNG văn bản này thì dùng lại, không gọi
        # Azure lần nữa. Sidecar bị xoá trước khi file bị tăng tốc nên file trong cache luôn là bản gốc.
        cached = _read_tts_cache(out_paths[i], current[i])
        if cached is not None:
            return cached
        if not _has_speakable_text(current[i]):
            # Whisper đôi khi trả câu chỉ có dấu câu ("." ở đoạn nhạc — job 33): Azure trả file 0 byte
            # làm hỏng cả chunk. Không gọi TTS, đặt khoảng lặng ngắn thay cho câu đó.
            return await _silent_result(out_paths[i])
        async with tts_sem:
            res = await azure_tts.synthesize(current[i], voice_name, str(out_paths[i]))
        if out_paths[i].exists() and out_paths[i].stat().st_size == 0:
            log.warning("Azure tra audio rong cho cau seq=%s (%r) — thay bang khoang lang", segments[i].seq, current[i])
            return await _silent_result(out_paths[i])
        _write_tts_cache(out_paths[i], current[i], res.duration_sec)
        return res

    current = list(texts)
    summarized = [False] * n
    results = list(await asyncio.gather(*(tts(i) for i in range(n))))
    t_orig = [Decimal(str(seg.duration)) for seg in segments]
    await _record_voice_chars_per_sec(voice_name, current, results)

    for _round in range(settings.max_resummarize_attempts):
        over = [
            i for i in range(n)
            if _speech_rate(t_orig[i], results[i].duration_sec) > R_UPPER_BOUND
            and float(t_orig[i]) >= settings.min_resummarize_frame_sec
        ]
        if not over:
            break
        # Số ký tự tối đa để về R ≈ 1.25 (chừa biên dưới trần 1.3), ước lượng theo tỉ lệ ký tự/giây
        # của chính câu vừa đọc.
        items = [
            (current[i], max(1, int(len(current[i]) * 1.25 * float(t_orig[i]) / max(results[i].duration_sec, 0.01))))
            for i in over
        ]
        try:
            shortened = await translation.resummarize_batch(items, target_language)
        except Exception as exc:  # rút gọn là tối ưu, lỗi thì rơi xuống nhánh tăng tốc tối đa
            log.warning("Rut gon theo lo that bai (%s cau) — dung tang toc: %s", len(over), exc)
            break
        changed = [i for i, text in zip(over, shortened) if text and text != current[i]]
        for i in changed:
            current[i] = shortened[over.index(i)]
            summarized[i] = True
        if not changed:
            break
        for i, res in zip(changed, await asyncio.gather(*(tts(i) for i in changed))):
            results[i] = res

    tempo_sem = asyncio.Semaphore(max(1, settings.tempo_concurrency))
    max_factor = float(_MAX_TEMPO)

    async def fit(i: int) -> azure_tts.SynthesisResult:
        r = _speech_rate(t_orig[i], results[i].duration_sec)
        if r <= R_LOWER_BOUND:
            return azure_tts.SynthesisResult(
                file_path=str(out_paths[i]), duration_sec=results[i].duration_sec,
                applied_rate=Decimal("1.0"), was_summarized=summarized[i],
            )
        if r > R_UPPER_BOUND:
            log.warning(
                "Segment seq=%s van R=%.2f > 1.3 sau rut gon — tang toc toi da x%s (BR-DUB-03), "
                "can Admin xem qua UC45/UC46", segments[i].seq, r, _MAX_TEMPO,
            )
        factor = min(float(r), max_factor)
        _tts_cache_path(out_paths[i]).unlink(missing_ok=True)
        async with tempo_sem:
            await audio_utils.change_tempo(out_paths[i], factor)
        return azure_tts.SynthesisResult(
            file_path=str(out_paths[i]), duration_sec=results[i].duration_sec / factor,
            applied_rate=Decimal(str(round(factor, 2))), was_summarized=summarized[i],
        )

    final = await asyncio.gather(*(fit(i) for i in range(n)))
    return [(final[i], current[i], summarized[i]) for i in range(n)]


async def _synthesize_with_adaptive_rate(
    segment: Segment, text: str, voice_name: str, out_path: Path, target_language: str,
) -> tuple[azure_tts.SynthesisResult, str, bool]:
    """Giữ chữ ký cũ cho script thực nghiệm NCKH (`NCKH/experiments/run_experiment.py`) — chạy
    `_synthesize_segments` cho 1 câu. Lưu ý: số liệu trong bài báo đo bằng bản CŨ (tăng tốc bằng
    `rate` của Azure, rút gọn từng câu); muốn tái lập đúng số liệu đó phải checkout commit cũ."""
    return (await _synthesize_segments([segment], [text], voice_name, [out_path], target_language))[0]


_TARGET_R = 1.15                  # bản dịch nhắm R ≈ 1.15: phần dư nhỏ tăng tốc cục bộ được, không cần rút gọn
_CPS_KEY = "dubbing:tts_cps:{voice}"


async def _voice_chars_per_sec(voice_name: str) -> float | None:
    """Tốc độ đọc (ký tự/giây) đã đo của giọng này ở các job trước — None nếu chưa có."""
    try:
        raw = await redis_client.get_client().get(_CPS_KEY.format(voice=voice_name))
        return float(raw) if raw else None
    except Exception as exc:  # chỉ là tối ưu: Redis lỗi thì dịch không kèm giới hạn ký tự như cũ
        log.warning("Khong doc duoc toc do doc cua giong %s: %s", voice_name, exc)
        return None


async def _record_voice_chars_per_sec(voice_name: str, texts: list[str], results: list[azure_tts.SynthesisResult]) -> None:
    """Đo tốc độ đọc thật của giọng từ lượt TTS đầu, lưu (làm mượt) để job sau ước `max_chars`.
    Không cần bảng tốc độ theo ngôn ngữ (BR-DUB-07: không hardcode danh sách ngôn ngữ)."""
    chars = sum(len(t) for t, r in zip(texts, results) if r.duration_sec > 0.3)
    secs = sum(r.duration_sec for r in results if r.duration_sec > 0.3)
    if chars < 50 or secs <= 0:
        return
    measured = chars / secs
    try:
        old = await _voice_chars_per_sec(voice_name)
        value = measured if old is None else 0.7 * old + 0.3 * measured
        await redis_client.get_client().set(_CPS_KEY.format(voice=voice_name), f"{value:.3f}")
    except Exception as exc:
        log.warning("Khong luu duoc toc do doc cua giong %s: %s", voice_name, exc)


def _read_json_list(path: Path, expected_len: int) -> list[str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, list) and len(data) == expected_len and all(isinstance(x, str) and x for x in data):
        return data
    return None


_SILENT_SEC = 0.1


def _has_speakable_text(text: str) -> bool:
    return any(ch.isalnum() for ch in text)


async def _silent_result(path: Path) -> azure_tts.SynthesisResult:
    await audio_utils.write_silence(path, _SILENT_SEC)
    return azure_tts.SynthesisResult(
        file_path=str(path), duration_sec=_SILENT_SEC, applied_rate=Decimal("1.0"), was_summarized=False,
    )


def _tts_cache_path(audio_path: Path) -> Path:
    return audio_path.with_name(audio_path.name + ".json")


def _read_tts_cache(audio_path: Path, text: str) -> azure_tts.SynthesisResult | None:
    try:
        meta = json.loads(_tts_cache_path(audio_path).read_text(encoding="utf-8"))
        if meta.get("text") != text or audio_path.stat().st_size == 0:
            return None
        return azure_tts.SynthesisResult(
            file_path=str(audio_path), duration_sec=float(meta["duration_sec"]),
            applied_rate=Decimal("1.0"), was_summarized=False,
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_tts_cache(audio_path: Path, text: str, duration_sec: float) -> None:
    try:
        if audio_path.stat().st_size > 0:
            _tts_cache_path(audio_path).write_text(
                json.dumps({"text": text, "duration_sec": duration_sec}, ensure_ascii=False), encoding="utf-8",
            )
    except OSError:
        pass


def _speech_rate(t_orig: Decimal, actual_duration_sec: float) -> Decimal:
    """R = T_exp / T_orig — xem ghi chú trong `_synthesize_segments` về lý do
    đảo chiều so với công thức "R = T_orig/T_exp" viết trong tài liệu.
    """
    if t_orig <= 0:
        return Decimal("0")
    return Decimal(str(actual_duration_sec)) / t_orig


def _chunk_key(ctx, chunk: ChunkPlan) -> str:
    return f"dubbing/{ctx.lesson_id}/{ctx.target_language}/chunk_{chunk.index}.mp3"


async def _upload_chunk_audio(path: Path, ctx, chunk: ChunkPlan) -> str:
    return await upload_file(path, _chunk_key(ctx, chunk))
