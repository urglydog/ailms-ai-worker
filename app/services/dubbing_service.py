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
import logging
import shutil
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app import audio_utils, media, redis_client
from app.config import settings
from app.http import backend_client
from app.models import Segment
from app.providers import edge_tts, groq_asr
from app.services import translation, tutor_indexing
from app.storage import upload_file

log = logging.getLogger(__name__)

MIN_SPEECH_RATIO = 0.10          # BR-DUB-10
R_UPPER_BOUND = Decimal("1.3")   # BR-DUB-03
R_LOWER_BOUND = Decimal("1.0")
MAX_TTS_RATE = "+30%"            # Mức tối đa của nhánh BR-DUB-03 khi hết lượt re-summarize


class SkippedPipelineError(Exception):
    """BR-DUB-10 — ký âm rỗng hoặc thoại < 10% thời lượng. TUYỆT ĐỐI không retry."""


class SourceUnavailableError(Exception):
    """BR-DUB-11 — nguồn video (URL B2 hoặc YouTube) không còn truy cập được."""


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


async def run_dubbing_pipeline(
    job_id: int, lesson_id: int, video_url: str, target_language: str, celery_task_id: str | None = None,
) -> dict:
    """Điểm vào duy nhất — gọi từ `app/tasks/dubbing.py::run_pipeline` qua `asyncio.run`."""
    work_dir = Path(settings.temp_dir) / f"job_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        ctx = await backend_client.get_context(job_id)

        source_audio = work_dir / "source.wav"
        try:
            if ctx.video_source == "YOUTUBE":
                await media.download_youtube_audio(ctx.video_url, source_audio)
            else:
                await media.extract_audio_from_url(ctx.video_url, source_audio)
        except Exception as exc:  # BR-DUB-11 — bất kỳ lỗi tải/tách nào đều coi là nguồn không khả dụng
            raise SourceUnavailableError(str(exc)) from exc

        duration_sec = ctx.duration_sec or int(await media.probe_duration_sec(source_audio))
        chunks = split_into_chunks(duration_sec, settings.chunk_minutes)
        await backend_client.start_job(job_id, total_chunks=len(chunks), celery_task_id=celery_task_id)

        reuse_source = ctx.source_transcript_available
        next_seq = 1
        chunk_audio_paths: list[Path] = []
        fallback_count = 0

        for chunk in chunks:
            try:
                chunk_audio, consumed_seq = await _process_chunk_with_retry(
                    job_id, ctx, chunk, source_audio, work_dir, reuse_source, next_seq,
                )
                next_seq += consumed_seq
                chunk_audio_paths.append(chunk_audio)
                await redis_client.publish_progress(
                    job_id, lesson_id, chunkIndex=chunk.index, totalChunks=len(chunks), status="COMPLETED",
                )
            except SkippedPipelineError:
                raise
            except Exception as exc:
                # BR-CHUNK-04: hết retry cho MỘT chunk — giữ audio GỐC riêng đoạn đó,
                # các chunk khác vẫn phát bản lồng tiếng bình thường.
                log.error("Chunk %s cua job %s that bai sau %s lan retry: %s", chunk.index, job_id, settings.max_retry, exc)
                fallback_count += 1
                fallback_audio = work_dir / f"chunk_{chunk.index}_original.mp3"
                await audio_utils.extract_range(source_audio, chunk.start_sec, chunk.end_sec, fallback_audio)
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

        final_path = work_dir / "final.mp3"
        await audio_utils.concat_files(chunk_audio_paths, final_path)
        final_duration = await audio_utils.measure_duration_sec(final_path)
        final_size = final_path.stat().st_size
        final_url = await upload_file(final_path, f"dubbing/{lesson_id}/{target_language}/final.mp3")

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
        # BR-STORAGE-01: dọn ngay sau job — cleanup_temp_files() (Celery beat) chỉ là
        # lưới an toàn cho thư mục mồ côi khi worker crash giữa chừng.
        shutil.rmtree(work_dir, ignore_errors=True)


async def _process_chunk_with_retry(
    job_id: int, ctx, chunk: ChunkPlan, source_audio: Path, work_dir: Path, reuse_source: bool, next_seq: int,
) -> tuple[Path, int]:
    """BR-CHUNK-04 — retry tối đa `MAX_RETRY` lần, exponential backoff. `SKIPPED`
    (raise `SkippedPipelineError`) KHÔNG được retry — phải bubble lên ngay.
    """
    last_error: Exception | None = None
    for attempt in range(1, settings.max_retry + 1):
        try:
            return await _process_chunk_once(job_id, ctx, chunk, source_audio, work_dir, reuse_source, next_seq)
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


async def _process_chunk_once(
    job_id: int, ctx, chunk: ChunkPlan, source_audio: Path, work_dir: Path, reuse_source: bool, next_seq: int,
) -> tuple[Path, int]:
    detected_language: str | None = None
    generate_source_dtos = False

    if reuse_source:
        segments = [
            Segment(seq=s.seq, start=float(s.start_sec), end=float(s.end_sec), text=s.text)
            for s in ctx.source_segments
            if chunk.start_sec <= float(s.start_sec) < chunk.end_sec
        ]
    else:
        chunk_wav = work_dir / f"chunk_{chunk.index}_src.wav"
        await audio_utils.extract_range(source_audio, chunk.start_sec, chunk.end_sec, chunk_wav)
        stt = await groq_asr.transcribe(str(chunk_wav))

        chunk_len = chunk.end_sec - chunk.start_sec
        if chunk_len <= 0 or (stt.speech_duration_sec / chunk_len) < MIN_SPEECH_RATIO:
            raise SkippedPipelineError(
                f"Chunk {chunk.index}: ty le loi thoai qua thap "
                f"({stt.speech_duration_sec:.1f}s / {chunk_len}s) — BR-DUB-10"
            )
        detected_language = stt.language
        generate_source_dtos = True
        segments = [
            Segment(seq=next_seq + i, start=chunk.start_sec + s.start, end=chunk.start_sec + s.end, text=s.text)
            for i, s in enumerate(stt.segments)
        ]

    if not segments:
        # Đoạn toàn khoảng lặng (hay gặp khi tái sử dụng transcript, chunk rơi đúng
        # vào quãng nghỉ) — giữ nguyên audio gốc cho đoạn này, không gọi AI.
        empty_audio = work_dir / f"chunk_{chunk.index}_dub.mp3"
        await audio_utils.extract_range(source_audio, chunk.start_sec, chunk.end_sec, empty_audio)
        audio_url = await _upload_chunk_audio(empty_audio, ctx, chunk)
        await backend_client.upsert_chunk_completed(
            job_id, chunk.index, start_sec=chunk.start_sec, end_sec=chunk.end_sec, audio_file_url=audio_url,
            detected_source_language=None, source_segments=None, target_segments=[],
        )
        return empty_audio, 0

    translated_texts = await translation.translate_batch(
        segments, ctx.source_language or detected_language or "unknown", ctx.target_language,
    )

    sentence_paths: list[Path] = []
    leading_silences: list[float] = []
    target_dtos: list[dict] = []
    source_dtos: list[dict] | None = [] if generate_source_dtos else None

    prev_end = float(chunk.start_sec)
    for seg, text in zip(segments, translated_texts):
        leading_silences.append(max(0.0, seg.start - prev_end))
        prev_end = seg.end

        out_path = work_dir / f"chunk_{chunk.index}_seg_{seg.seq}.mp3"
        result, final_text, was_summarized = await _synthesize_with_adaptive_rate(
            seg, text, ctx.voice_name, out_path, ctx.target_language,
        )
        sentence_paths.append(out_path)

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
        try:
            await tutor_indexing.index_segments(ctx.lesson_id, detected_language, segments)
        except Exception as exc:
            log.warning("Danh index embedding cho lesson %s that bai (khong anh huong job long tieng): %s", ctx.lesson_id, exc)

    chunk_audio = work_dir / f"chunk_{chunk.index}_dub.mp3"
    await audio_utils.concat_with_leading_silence(sentence_paths, leading_silences, chunk_audio)
    trailing_gap = max(0.0, chunk.end_sec - prev_end)
    if trailing_gap > 0.05:
        await audio_utils.pad_silence(chunk_audio, trailing_gap)

    audio_url = await _upload_chunk_audio(chunk_audio, ctx, chunk)
    await backend_client.upsert_chunk_completed(
        job_id, chunk.index, start_sec=chunk.start_sec, end_sec=chunk.end_sec, audio_file_url=audio_url,
        detected_source_language=detected_language, source_segments=source_dtos, target_segments=target_dtos,
    )

    return chunk_audio, len(segments) if generate_source_dtos else 0


async def _synthesize_with_adaptive_rate(
    segment: Segment, text: str, voice_name: str, out_path: Path, target_language: str,
) -> tuple[edge_tts.SynthesisResult, str, bool]:
    """BR-DUB-03 với trần an toàn `MAX_RESUMMARIZE_ATTEMPTS` (doc/SETUP_GIAIDOAN5.md
    mục 4 — văn bản BR gốc không có điều kiện dừng, nếu lặp y nguyên sẽ có nguy cơ vô
    hạn khi câu đã quá ngắn mà R vẫn > 1.3):

        lần lặp = 0
        while R > 1.3 và lần lặp < MAX_RESUMMARIZE_ATTEMPTS:
            gọi LLM rút gọn thêm; tính lại R; lần lặp += 1
        nếu R vẫn > 1.3 sau khi hết số lần cho phép:
            chấp nhận rate = +30% (mức tối đa của nhánh BR-DUB-03); ghi log cảnh báo
    """
    t_orig = Decimal(str(segment.duration))
    current_text = text
    was_summarized = False

    result = await edge_tts.synthesize(current_text, voice_name, str(out_path))
    r = _speech_rate(t_orig, result.duration_sec)
    # LƯU Ý (đối chiếu với bản Word gốc trước khi bảo vệ): tài liệu (DEVELOPMENT_PLAN.md,
    # skill lms-dubbing-pipeline, business-rules.md) đều viết công thức "R = T_orig/T_exp"
    # nhưng NẾU áp dụng đúng y văn bản đó thì nhánh "1.0 < R ≤ 1.3 → tăng tốc" chỉ xảy ra
    # khi audio tổng hợp NGẮN hơn T_orig — tăng tốc audio vốn đã ngắn là vô nghĩa, và mâu
    # thuẫn với chính core/_8_2_dub_chunks.py (VideoLingo gốc): họ tăng tốc khi
    # est_dur (~T_exp) VƯỢT QUÁ khung thời gian gốc. `_speech_rate()` dưới đây vì vậy tính
    # R = T_exp / T_orig (audio thực tế / khung gốc) — giữ NGUYÊN 3 mốc 1.0/1.3 và hành
    # động ở mỗi nhánh đúng như tài liệu, chỉ đảo chiều tỉ số để hành vi có ý nghĩa.

    attempts = 0
    while r > R_UPPER_BOUND and attempts < settings.max_resummarize_attempts:
        current_text = await translation.resummarize(current_text, target_language)
        was_summarized = True
        result = await edge_tts.synthesize(current_text, voice_name, str(out_path))
        r = _speech_rate(t_orig, result.duration_sec)
        attempts += 1

    if r > R_UPPER_BOUND:
        log.warning(
            "Segment seq=%s van R=%.2f > 1.3 sau %s lan rut gon (tran %s) - chap nhan rate %s (BR-DUB-03), "
            "can Admin xem qua UC45/UC46",
            segment.seq, r, attempts, settings.max_resummarize_attempts, MAX_TTS_RATE,
        )
        result = await edge_tts.synthesize(current_text, voice_name, str(out_path), rate=MAX_TTS_RATE)
    elif r > R_LOWER_BOUND:
        result = await edge_tts.synthesize(current_text, voice_name, str(out_path), rate=edge_tts.compute_rate_flag(r))
    else:
        pad_sec = float(t_orig) - result.duration_sec
        if pad_sec > 0.05:
            await audio_utils.pad_silence(out_path, pad_sec)

    return result, current_text, was_summarized


def _speech_rate(t_orig: Decimal, actual_duration_sec: float) -> Decimal:
    """R = T_exp / T_orig — xem ghi chú trong `_synthesize_with_adaptive_rate` về lý do
    đảo chiều so với công thức "R = T_orig/T_exp" viết trong tài liệu.
    """
    if t_orig <= 0:
        return Decimal("0")
    return Decimal(str(actual_duration_sec)) / t_orig


async def _upload_chunk_audio(path: Path, ctx, chunk: ChunkPlan) -> str:
    key = f"dubbing/{ctx.lesson_id}/{ctx.target_language}/chunk_{chunk.index}.mp3"
    return await upload_file(path, key)
