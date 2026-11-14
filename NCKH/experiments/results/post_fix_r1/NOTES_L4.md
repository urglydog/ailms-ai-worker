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

## Cập nhật 14/11/2026 — bỏ AI, hai người chấm (bản dùng trong bài báo)

| Mục | Giá trị |
|---|---|
| Người chấm 1 | Thiện (cột `score_rater2` cũ), so với câu tiếng Anh gốc |
| Người chấm 2 | Sang, chấm độc lập (không xem điểm người khác/AI), so với bản dịch đầy đủ V2; file chấm `fidelity_cham_Sang.csv` |
| Đồng thuận ban đầu | 31/50 (62%); Cohen kappa 0,024; kappa trọng số bậc hai −0,043; Gwet AC1 0,53 (`fidelity_summary_human.json`) |
| Thống nhất | 19 câu lệch, hai người thống nhất theo cùng chuẩn bản dịch đầy đủ (`fidelity_thong_nhat_19cau.csv`, id 37 bị Excel đổi thành 0 đã sửa lại); #16 đổi 2 → 1 sau khi rà (gộp hai ý thành quan hệ nhân quả sai) |
| Điểm cuối | 2: 36 (72%) · 1: 12 (24%) · 0: 2 (4%, câu #4 và #37); trung bình 1,68/2 (`fidelity_scores_human.csv`, cột `score_final_consensus`) |
| AI | Điểm của Claude **không dùng** trong bài báo; giữ `fidelity_tham_khao_Claude.csv` làm tham khảo |
