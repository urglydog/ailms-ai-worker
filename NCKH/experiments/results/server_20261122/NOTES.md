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
| Giọng đọc C4 (4 job thật qua web) | `ko-KR-SunHiNeural`, ngôn ngữ `ko-KR` |

## Trạng thái trước/sau build (A0, A4, A5)
- Trước khi build lại: `.env` đã có đúng 3 biến mới (`gemini-3.6-flash`, `minimal`, `modal`), container nạp `.env` từ 21/11 13:12 UTC, ffmpeg 7.1.5. **Thiếu gói `modal`** trong image (`ModuleNotFoundError`) nên tách nhạc nền sẽ lỗi.
- Sau khi build lại và tạo lại riêng container `ai-worker` (22/11 ~13:27 UTC): `import modal` ok, `modal.Function.from_name('lms-demucs','separate').hydrate()` ok, gọi thử Gemini 1 lần ra `ok`, Celery 1 node online, container `running restarts=0 oom=false`.
- Không có job lồng tiếng nào đang chạy lúc build lại (kiểm bằng `celery inspect active`).

## Dữ liệu KHÔNG xóa (khác hướng dẫn gốc)
Thiện **từ chối** bước A6 (xóa dữ liệu lồng tiếng cũ của 4 bài 2284, 2285, 2286, 2288). Hệ quả:
- C1–C3, C5 (script) không bị ảnh hưởng: script có cache ASR riêng (`.cache/`, đã đổi tên bản cũ thành `.cache_old_e5a8cb7/`) và không ghi vào DB.
- C4 (job thật) dùng ngôn ngữ **ko-KR** (chưa có bản lồng tiếng) thay vì tiếng Việt. Bản ký âm gốc của 4 bài được **dùng lại** (`asr=0.0 s`, mốc đầu câu là mốc CŨ kiểu đầu đoạn). Nhạc nền: cả 4 job đều **tách mới** (log `BGM tach nhac xong`, không có `dung lai`), nên số `nhạc` là số thật.
- Redis `dubbing:tts_cps:*`: trước phiên hai giọng vi-VN (HoaiMy, NamMinh) đều chưa có khóa (khóa SunHi chưa kiểm tra trước job 17). Lần chạy thử `smoke_real2` đã ghi `vi-VN-HoaiMyNeural = 13.183`; **đã xóa đúng khóa này** (Thiện đồng ý) trước C1 để trả về trạng thái trước phiên. Các khóa khác không bị xóa.

## `tts_cps` (ký tự/giây) cuối đợt đo
`vi-VN-HoaiMyNeural` 11.052; `vi-VN-NamMinhNeural` 10.683; `ko-KR-SunHiNeural` 4.887.

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
| `server_20261122` | C4: job 17, 18, 19, 20 (lesson 2284, 2285, 2286, 2288, ko-KR) | cả 4 `COMPLETED` |

## Thay đổi script
`NCKH/experiments/run_experiment_v2.py`: thêm thử lại tối đa 3 lần khi lời gọi dịch V1 trả JSON hỏng (`translate_v1`). Mỗi lần thử vẫn tính vào số lời gọi LLM của V1. Không sửa gì trong `app/`.

## Chưa làm / không có
- Không chạy `server_job_stats.py`/`server_job_stats_ext.sql` (cần mật khẩu MySQL). Trạng thái job lấy từ kết quả Celery (`COMPLETED`) và log.
- Không có số tiền chính xác của từng job (bảng `ai_usage_logs` chưa truy vấn). Xem REPORT mục Chi phí.
- Chấm L4 (C5) chưa thực hiện: file mẫu đã tạo, chờ Sang và Thiện chấm độc lập.
