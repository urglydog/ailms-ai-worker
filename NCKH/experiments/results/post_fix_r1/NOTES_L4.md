# NOTES — L4 độ trung thành nội dung (post_fix_r1)

| Mục | Giá trị |
|---|---|
| Mẫu | 50 câu rút gọn của V4 (`was_summarized = True`, khung gốc ≥ 2 s), seed 42, chọn từ 214 câu; sinh bằng `python NCKH/experiments/sample_fidelity.py NCKH/experiments/results/post_fix_r1 --n 50 --seed 42 --min-frame 2.0` (tái lập được) |
| Thang | 2 = giữ đủ ý · 1 = mất ý phụ · 0 = mất/sai ý chính; chấm V4 so với câu tiếng Anh gốc |
| **Người chấm 1** | **Mô hình ngôn ngữ (Claude)**, điểm và lý do từng câu ở `fidelity_tham_khao_Claude.csv`. Đây là điểm do mô hình tạo ra, **không phải người** |
| **Người chấm 2** | **Một người** (theo xác nhận của Thiện 13/11/2026): chấm **trước khi xem điểm của mô hình** |
| Điểm đưa vào `fidelity_scores.csv` | `score_rater1` = người chấm 1 (Claude, nguyên điểm gốc, không chỉnh); `score_rater2` = người chấm 2 |
| Ghi chú | Trong một lần dán trước đó có 3 câu (3, 33, 34) của cột "người chấm 1" bị sửa từ 1 lên 2; đã **khôi phục về điểm gốc của Claude** theo quyết định của Thiện (phương án B) |
| Kết quả | `fidelity_summary.md/json` (đồng thuận tuyệt đối 86,0%; kappa trọng số bậc hai 0,757; Gwet's AC1 0,819; điểm bảo toàn ý trung bình 1,65/2) |
| Giới hạn | Một trong hai người chấm là mô hình AI, nên đây **không phải hai người chấm độc lập**; kết quả cần được diễn giải đúng như vậy trong bài |
