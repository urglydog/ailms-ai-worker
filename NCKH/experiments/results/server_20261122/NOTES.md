# NOTES đợt đo sau tối ưu dubbing (đợt 3) — 22/11/2026

Người đo: Thiện (cùng Claude). Server: `ubuntu-4gb-fsn1-2` (3,8 GB RAM, đĩa 38 GB).

## Cấu hình cố định suốt đợt đo
| Mục | Giá trị |
|---|---|
| Commit ai-worker | `0d866b9` (nhánh `feat/additional-features`, đã gồm `origin/NCKH`). `run_meta.json` ghi `commit: "?"` vì container không đọc được git, nên ghi tay ở đây |
| Image `be-ai-worker` | build lại 22/11/2026 (bổ sung gói `modal==1.6.4`); `ai-api`, `ai-beat` KHÔNG build lại |
| ffmpeg / Debian | 7.1.5 / 13.7 |
| `GEMINI_MODEL` / `GEMINI_MODELS` | `gemini-3.6-flash` / để trống (không model dự phòng) |
| `DUBBING_THINKING_LEVEL` | `minimal` |
| `BGM_SEPARATION` | `modal` (nhạc nền BẬT) |
| `TIMELINE_ENGINE`, `CHUNK_MINUTES`, `MAX_RESUMMARIZE_ATTEMPTS`, `MIN_RESUMMARIZE_FRAME_SEC`, `TTS_CONCURRENCY` | `ffmpeg`, 10, 2, 2.0, 16 |
| ASR | `whisper-large-v3-turbo` (Groq) |
| Giọng đọc đo bằng script (C1–C3, C5) | `vi-VN-HoaiMyNeural` (lec01, lec03), `vi-VN-NamMinhNeural` (lec02, lec04) — file `videos.json` không đổi |
| Giọng đọc C4 (4 job thật qua web) | Lần 2 (chính): `vi-VN-HoaiMyNeural` (lec01, lec03), `vi-VN-NamMinhNeural` (lec02, lec04). Lần 1 (bổ sung): `ko-KR-SunHiNeural` |

## Trạng thái trước/sau build (A0, A4, A5)
- Trước khi build lại: `.env` đã có đúng 3 biến mới (`gemini-3.6-flash`, `minimal`, `modal`), container nạp `.env` từ 21/11 13:12 UTC, ffmpeg 7.1.5. **Thiếu gói `modal`** trong image (`ModuleNotFoundError`) nên tách nhạc nền sẽ lỗi.
- Sau khi build lại và tạo lại riêng container `ai-worker` (22/11 ~13:27 UTC): `import modal` ok, `modal.Function.from_name('lms-demucs','separate').hydrate()` ok, gọi thử Gemini 1 lần ra `ok`, Celery 1 node online, container `running restarts=0 oom=false`.
- Không có job lồng tiếng nào đang chạy lúc build lại (kiểm bằng `celery inspect active`).

## Xóa dữ liệu 4 bài (bước A6) — làm SAU lần ko-KR, theo yêu cầu của Sang
Ban đầu Thiện từ chối xóa nên C4 chạy lần 1 bằng ko-KR (dùng lại bản ký âm, `asr=0`). Sau đó Sang yêu cầu chạy tiếng Việt và xóa dữ liệu cũ; Thiện đồng ý (22/11/2026, xóa xong khoảng 22:25 giờ Việt Nam) và **bỏ qua bước sao lưu** (script `backup_4lessons.sh` đã viết nhưng không chạy).
- **MySQL** (`reset_lessons.sql`, chạy trong 1 transaction; Thiện tự nhập mật khẩu): đã xóa, theo từng lesson 2284 / 2285 / 2286 / 2288: `ai_jobs` 3/3/2/3, `audio_tracks` 3/3/2/3, `transcripts` 4/4/4/4, cùng các bảng con (`ai_job_chunks`, `audio_chunks`, `transcript_segments`). Kiểm tra sau xóa: 0 dòng ở cả 3 bảng. Script xóa **mọi ngôn ngữ** của 4 bài, nên bản ko-KR vừa chạy cũng mất.
- **B2** (`reset_lessons_cache.py --apply`): 8 object (`bgm/2284..2288/<hash>/music.mp3` và `vocals.mp3`, mỗi bài 2 file, là nhạc tách của lần ko-KR).
- **Redis:** xóa `dubbing:tts_cps:vi-VN-HoaiMyNeural` (đang là 11,052) và `...NamMinhNeural` (10,683); xóa 1 khóa `courseDetails::*`. Khóa SunHi giữ nguyên (4,887).
- `reset_lessons_cache.py` lỗi ở phần Redis (client bất đồng bộ) và đã được sửa bằng `asyncio`; `reset_lessons.sql` được thêm cảnh báo "xóa mọi ngôn ngữ".
- Hệ quả: lần chạy C4 tiếng Việt (job 21–24) là lần lồng tiếng đầu thật sự: ASR chạy đầy đủ, nhạc tách mới.
- C1–C3, C5 (script) không bị ảnh hưởng: script có cache ASR riêng (`.cache/`, bản cũ đổi tên thành `.cache_old_e5a8cb7/`), không ghi vào DB.
- Redis trước phiên: hai giọng vi-VN (HoaiMy, NamMinh) chưa có khóa `tts_cps`; lần chạy thử `smoke_real2` ghi `HoaiMy = 13.183` và đã xóa đúng khóa đó trước C1 (Thiện đồng ý).

## `tts_cps` (ký tự/giây) cuối đợt đo
`vi-VN-HoaiMyNeural` 12.264; `vi-VN-NamMinhNeural` 12.416; `ko-KR-SunHiNeural` 4.887. (Giữa đợt, trước khi xóa: HoaiMy 11.052, NamMinh 10.683.)

## Nhật ký các lần chạy
| Run | Việc | Kết quả |
|---|---|---|
| `smoke_real` | B3 lần 1 (lec01, 1 chunk) | LỖI: Gemini trả JSON hỏng (`invalid_response`), không dùng |
| `smoke_real2` | B3 lần 2 | chạy được; làm ghi `tts_cps` HoaiMy 13.183 (đã xóa khóa); không dùng |
| `v3_r1` | C1 4 bài | lec02–04 xong; **lec01 lỗi JSON ở V1** |
| `v3_r1_lec01` | chạy bù lec01 | lỗi JSON lần nữa (cùng vị trí) |
| `v3_r1_lec01b` | chạy bù lec01 sau khi thêm thử lại V1 vào script | xong, V1 không cần thử lại |
| `v3_r1_merged` | gộp `v3_r1` (lec02–04) + `v3_r1_lec01b` (lec01) | số liệu chính của C1, C3, C5 |
| `v3_r2` | C2: V4 lần 2, 4 bài | xong |
| `server_20261122` | C4 lần 1: job 17–20 (lesson 2284, 2285, 2286, 2288, ko-KR, dùng lại ký âm) | cả 4 `COMPLETED` |
| `server_20261122_vi` | C4 lần 2 (chính): job 21–24 (cùng 4 bài, vi-VN, sau khi xóa dữ liệu) | cả 4 `COMPLETED`, 14,5–19,3 s/phút video |

## Thay đổi script
`NCKH/experiments/run_experiment_v2.py`: thêm thử lại tối đa 3 lần khi lời gọi dịch V1 trả JSON hỏng (`translate_v1`). Mỗi lần thử vẫn tính vào số lời gọi LLM của V1. Không sửa gì trong `app/`.

## Chưa làm / không có
- Không chạy `server_job_stats.py`/`server_job_stats_ext.sql` (cần mật khẩu MySQL). Trạng thái job lấy từ kết quả Celery (`COMPLETED`) và log; chưa đối chiếu `retry_count` ở DB.
- Không có số tiền chính xác của từng job (bảng `ai_usage_logs` chưa truy vấn). Xem REPORT mục Chi phí.
- Chấm L4 (C5) chưa thực hiện: file mẫu đã tạo, chờ Sang và Thiện chấm độc lập.
