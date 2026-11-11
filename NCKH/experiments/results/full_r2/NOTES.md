# NOTES — run `full_r2` (L3, lần lặp 1) — **KHÔNG HOÀN CHỈNH, không dùng làm số liệu**

| Mục | Giá trị |
|---|---|
| Commit ai-worker | `11378e5` (cây làm việc như `full_r1`) |
| Lệnh | `docker exec --user 1000:1001 lms_ai_worker python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r2 --variants V2,V4 --keep-audio` |
| Thời gian | 2026-11-10 20:28:17 – 20:52:07 UTC |
| Kết quả | Chỉ `lec01` xong (131 câu × V2, V4 = 262 dòng). `lec02`: lỗi `Max retries exceeded for Gemini API`; `lec03`, `lec04`: `No active Gemini slot available (all in cooldown)` |
| Nguyên nhân | Gemini API trả **HTTP 402 RESOURCE_EXHAUSTED — "Your prepayment credits are depleted"** (xác nhận bằng một lần gọi thử lúc ~20:55 UTC). Log của pipeline không phân biệt lỗi này, chỉ ghi "network error"/"cooldown" |
| File | `summary.md/json`, `drift_summary.*` trong thư mục này **chỉ phản ánh `lec01`** (do chuỗi lệnh tự chạy `analyze.py` trên dữ liệu dở dang) |
| Việc cần làm | Nạp credit Gemini, chạy lại với run-id mới (ví dụ `full_r2b`); giữ nguyên thư mục này để minh bạch |
