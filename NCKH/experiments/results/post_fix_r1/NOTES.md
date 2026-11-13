# NOTES — run `post_fix_r1` (pipeline sau bản sửa 11–13/11/2026, V1–V4, toàn bộ 4 bài)

| Mục | Giá trị |
|---|---|
| Commit ai-worker | `4ab708f` (Merge PR #58: bản sửa của Sang gồm xếp câu theo mốc tuyệt đối, kẹp mốc ASR, phát hiện 402, câu < 2 s không rút gọn, bỏ đệm lặng trong file câu) |
| Người chạy | Claude Code theo yêu cầu của Thiện (user `dev-thien`) |
| Thời gian | 2026-11-13 09:53:53 UTC đến ~11:55 UTC |
| Lệnh | `docker exec --user 1000:1001 lms_ai_worker python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id post_fix_r1 --keep-audio` |
| Máy | Như `full_r1`: Ubuntu 22.04, 2 vCPU Intel Xeon Skylake, 3,7 GiB RAM, dùng chung với hệ thống đang vận hành |
| Container | `lms_ai_worker` tạo lại lúc 09:53 UTC với cấu hình log `json-file` 10 MB × 3; code bind-mount từ `/var/lms/ai-worker` |
| Tham số (từ `run_meta.json`) | `chunk_minutes=10`, `r_min=1,0`, `r_max=1,3`, `max_tts_rate=+30%`, `max_resummarize_attempts=2`, `min_resummarize_frame_sec=2,0`, ASR `whisper-large-v3-turbo`, LLM `gemini-3.5-flash` |
| ASR | Dùng cache (`asr_cache=True`) của `full_r1` cho cả 4 bài |
| Số lần gọi Gemini | `lec01` 73, `lec02` 112, `lec03` 69, `lec04` 32 → **286**; chi phí khoảng 44K₫ (143K → 99K, ~154₫/lần gọi) |
| Kiểm tra bài đầu | Không lỗi/402; câu khung < 2 s có 0 lần rút gọn; không câu nào có `t_final < t_orig`; đủ 3148 dòng (787 câu × 4 phương án) |
| Ghép audio thật | `check_full_length.py --variants V2,V4 --assembly new` → `check_full_length.md/json`, `drift_measured.csv`; V3 không kiểm (không lưu file câu nhánh `pad`) |
| Sự cố | Không có |
| Ghi chú | Trong lúc chạy, `lms_ai_api` từng reload vì file trong `NCKH/` đổi (đã chặn bằng `--reload-exclude`); không ảnh hưởng run vì run chạy trong `lms_ai_worker` |
| L4 | `fidelity_*`, `NOTES_L4.md` |
