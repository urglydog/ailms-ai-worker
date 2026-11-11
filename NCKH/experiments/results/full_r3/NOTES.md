# NOTES — run `full_r3` (L3, lần lặp 2) — **THẤT BẠI, không có dữ liệu**

| Mục | Giá trị |
|---|---|
| Commit ai-worker | `11378e5` |
| Lệnh | `docker exec --user 1000:1001 lms_ai_worker python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r3 --variants V2,V4 --keep-audio` |
| Thời gian | 2026-11-10 20:52:08 – 20:52:11 UTC (3 giây) |
| Kết quả | Cả 4 bài lỗi ngay ở lời gọi Gemini; không có `segments.csv`, `videos.csv`, `summary.*` |
| Nguyên nhân | Credit prepay Gemini đã hết (HTTP 402 RESOURCE_EXHAUSTED) — xem `../full_r2/NOTES.md` |
| Việc cần làm | Nạp credit, chạy lại với run-id mới; giữ nguyên thư mục này |
