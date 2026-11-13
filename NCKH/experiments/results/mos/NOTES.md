# NOTES — MOS (L5): KHÔNG THỰC HIỆN

Quyết định của Thiện ngày 13/11/2026: **bỏ đánh giá cảm nhận người nghe (MOS)** trong đợt này, không có đủ người nghe thật trước hạn nộp bài. Bài báo ghi rõ đây là hạn chế và hướng phát triển.

| Mục | Ghi chú |
|---|---|
| Đã chuẩn bị | Công cụ chọn đoạn, ghép clip có hình, phân tích (`mos_select_clips.py`, `mos_make_clips.py`, `mos_analyze.py`, mẫu form `mos_form_template.md`); đã tạo thử 40 clip (20 đoạn × V2, V4) từ `post_fix_r1` và đã thử chuỗi phân tích bằng dữ liệu giả trong thư mục tạm |
| **Dữ liệu mẫu** | Một file CSV phản hồi mẫu (`mos_responses.csv`, 40 dòng) **được tạo ra để thử công cụ, không phải phản hồi của người nghe thật**: dấu thời gian nằm trước lúc các clip được tạo (08:11–18:13 ngày 13/11 trong khi clip tạo lúc 20:19) và điểm V2 gần như bằng V4. **Không dùng trong bất kỳ kết quả nào** và không được commit |
| Giới hạn thiết kế của bộ clip (nếu làm sau) | Clip ghép riêng từng đoạn 15–25 giây nên trễ tích lũy của V2 từ đầu bài không được tính vào clip (thiên lệch có lợi cho V2) |
| Việc làm sau | Khảo sát người nghe thật (≥ 10 người, độc lập với nhóm tác giả) trên bản code cuối, kèm 2 clip luyện tập |
