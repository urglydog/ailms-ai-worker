# NOTES — run `full_r1` (L2: chạy toàn bộ độ dài, V1–V4)

| Mục | Giá trị |
|---|---|
| Commit ai-worker | `11378e5` (Merge PR #53 vào develop, ngày 10/11/2026) — cây làm việc chỉ khác ở `videos.json` (chỉ sửa trường `note`) và các script mới trong `NCKH/experiments/` |
| Người chạy | Claude Code theo yêu cầu của Thiện (user `dev-thien` trên server) |
| Bắt đầu / kết thúc | 2026-11-10 17:20:18 / 20:11:02 (giờ UTC của server) |
| Lệnh | `docker exec --user 1000:1001 lms_ai_worker python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r1 --keep-audio` |
| Chạy ở đâu | Container `lms_ai_worker` (image `be-ai-worker`), bind-mount `/var/lms/ai-worker` → `/app`, chạy bằng uid 1000:gid 1001 (không phải root) |
| Máy (L6) | Ubuntu 22.04.5 LTS, kernel 5.15.0-198-generic; 2 vCPU Intel Xeon (Skylake, IBRS); RAM 3,7 GiB; ổ đĩa 38 GB (còn 3,3 GB); Docker 29.9.2; host `ubuntu-4gb-fsn1-2` |
| Mạng | **Chưa đo** tốc độ tải lên/xuống |
| Tham số (từ `run_meta.json`) | `chunk_minutes=10`, `r_min=1.0`, `r_max=1.3`, `max_tts_rate=+30%`, `max_resummarize_attempts=2`, `min_speech_ratio=0.1`, ASR `whisper-large-v3-turbo`, LLM `gemini-3.5-flash` (không có model dự phòng), giọng đọc Azure Neural theo `videos.json` (`vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural`) |
| `max_chunks` | Không giới hạn (đợt 1 dùng `--max-chunks 1`) |
| ASR | `lec01`: dùng cache đợt 1 (1 đoạn, đủ cả bài). `lec02`–`lec04`: gọi Groq lại cho toàn bài (`asr_cache=False`) |

## Lưu ý quan trọng khi đọc số liệu

1. **Máy dùng chung với hệ thống đang chạy thật** (backend, MySQL, Redis, Caddy…) và chỉ có 2 vCPU/3,7 GiB RAM.
   Các số **thời gian xử lý** (`asr/translate/tts … sec_per_min`) bị ảnh hưởng bởi tải chung và chạy tuần tự
   từng câu, **không đại diện cho server vận hành**. Chỉ số chất lượng (Δ, R, số lần gọi LLM/TTS) không phụ thuộc tải máy.
2. Mọi video trong manifest đều thuộc nhóm CNTT về nội dung, dù `videos.json` gắn nhãn `category=KyNangMem`
   cho `lec03` (*Crash Course CS #29: The Internet*) và `lec04` (*Stanford CS229, Lecture 1*). **Nhãn nhóm trong
   `segments.csv`/`videos.csv` của run này không phản ánh đúng nội dung.** Chưa sửa vì sẽ làm `run_meta` không khớp thực tế.
3. Đầu vào là **audio mp3** tách từ video, không phải video. Không đánh giá được độ khớp hình.
4. Với V3, các câu thuộc nhánh `pad` không lưu file audio riêng (dùng chung kết quả V2), nên
   `check_full_length.py` chỉ kiểm V2 và V4.

## Sự cố / thay đổi trong quá trình thực hiện

- Trước khi chạy: `git pull` lỗi `Permission denied` ở `results/20261109_042122/` vì thư mục thuộc `root`
  (tạo từ lần chạy đợt 1 bằng root). Đã `chown` về `dev-thien:lms-group` rồi pull thành công.
- Dọn dung lượng: `docker builder prune -f` (giải phóng 2,11 GB build cache). Không đụng volume, image, container hay DB.
- Trong lúc `full_r1` chạy, đã sửa trường `note` của `videos.json` (thêm nguồn). Không đổi tham số, id, đường dẫn
  hay giọng đọc nên không ảnh hưởng kết quả; `run_meta.json` của run này vẫn giữ `note` cũ.
- Không có lỗi, không có lần chạy lại. Log ghi nhiều cảnh báo `R > 1.3 sau 2 lần rút gọn — chấp nhận +30%`
  (đây là hành vi thiết kế, không phải lỗi).
