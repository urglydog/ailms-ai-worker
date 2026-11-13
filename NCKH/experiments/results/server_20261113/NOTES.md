# NOTES — số liệu 4 tác vụ lồng tiếng thật (khóa học thử nghiệm 92)

| Mục | Giá trị |
|---|---|
| Khóa học | Khóa **92** "Nền tảng khoa học máy tính" (Nháp, không công khai), tài khoản giảng viên của Thiện |
| Bài học / job | `lec01` = lesson 2284 / job 10 · `lec02` = 2285 / job 11 · `lec03` = 2286 / job 12 · `lec04` = 2288 / job 13 (lesson 2287 từng xuất hiện trong log, không có job) |
| Video | 4 file mp4 480p tải từ YouTube về máy cá nhân rồi upload qua giao diện (không dùng link YouTube); thời lượng khớp audio ±0,04 s; `lec04` cắt 15 phút đầu |
| Ngôn ngữ / giọng | `vi-VN`; `lec01`, `lec03`: Hoai My; `lec02`, `lec04`: Nam Minh (như thí nghiệm) |
| Commit đang chạy | `4ab708f` (sau khi tạo lại container 13/11 09:53 UTC) |
| Cách lấy số liệu | `server_job_stats_ext.sql` (chỉ SELECT, không lấy email/tên/nội dung/URL) chạy trong `lms_mysql` do Thiện tự nhập mật khẩu; `analyze_server.py` → `server_summary.md/json` |
| Giờ bấm | job 10: 19:19:35 · job 11: 19:41:03 · job 12: 20:22:52 · job 13: 21:43:50 (giờ Việt Nam) |
| Job bị loại | Không có (4/4 `COMPLETED`, 0 lần thử lại) |
| Điều kiện đo (ảnh hưởng thời gian) | Mỗi job chạy **một mình** (không có job lồng tiếng khác chạy đồng thời), trên máy dùng chung với hệ thống vận hành. Việc Thiện tải 4 file mp4 lên server diễn ra 12:38–12:42 UTC, trùng vài phút đầu job 11; các việc nặng khác (làm clip MOS) được dời sang khoảng giữa các job. Các việc nhẹ (đọc log, chạy script phân tích) có thể chạy đồng thời |
| Hạn chế | Chưa có bài lồng sang ngôn ngữ thứ hai → chưa đo tái sử dụng bản ký âm; `play_count` = 0 (chưa có lượt phát) |
| ASR | Bản ký âm gốc chưa có sẵn khi bấm lồng tiếng nên **ASR nằm trong thời gian xử lý** của job |
