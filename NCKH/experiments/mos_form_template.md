# Mẫu Google Form chấm MOS (L5) — lồng tiếng tiếng Việt cho bài giảng tiếng Anh

Dùng để tạo form thủ công (không lưu link công khai trong repo). Ẩn danh: **không** hỏi tên, email, trường; chỉ cần mã người nghe.

## Phần giới thiệu (hiển thị đầu form)
Cảm ơn bạn đã tham gia khảo sát (~15 phút). Bạn sẽ xem **40 đoạn video ngắn (15–25 giây)** của các bài giảng công nghệ thông tin
bằng tiếng Anh, được lồng tiếng Việt tự động. Hãy dùng tai nghe, xem hết mỗi đoạn rồi chấm điểm 3 tiêu chí theo thang **1–5**
(1 = rất kém, 5 = rất tốt):
1. **Độ tự nhiên của giọng đọc** — nghe có tự nhiên, trôi chảy, tốc độ thoải mái không?
2. **Độ dễ hiểu** — nội dung lời nói có dễ hiểu không?
3. **Độ khớp giữa tiếng và hình** — lời nói có xuất hiện đúng lúc với hình minh họa/thao tác trên màn hình không?

Dữ liệu chỉ dùng cho nghiên cứu, không thu thập thông tin cá nhân. Bạn có thể dừng bất cứ lúc nào.

## Điều kiện tham gia (câu hỏi đầu form, loại nếu "Không")
- Bạn nghe và hiểu tiếng Việt tốt? (Có/Không)
- Bạn **không** thuộc nhóm tác giả bài báo? (Đúng/Không đúng)

## Câu hỏi thông tin
- Mã người nghe (do người tổ chức cấp, dạng P01, P02…): ______
- Thiết bị nghe: Tai nghe / Loa ngoài (chọn một)

## 2 clip luyện tập (không tính điểm)
Cho 2 clip đầu tiên để làm quen thang điểm (nên dùng 2 clip ngoài danh sách 40 clip). Ghi rõ "Clip luyện tập — không tính điểm".

## Mỗi clip (lặp 40 lần, thứ tự xáo trộn khác nhau cho từng người; nên làm 2 phiếu có thứ tự khác nhau)
- Tiêu đề: Clip C### (mã trong `clips_key.csv`, **không** ghi tên phương án)
- Video nhúng (liên kết riêng tư/không công khai)
- Ba câu hỏi dạng lưới 1–5: `naturalness`, `intelligibility`, `sync`

## Xuất dữ liệu
Xuất phản hồi ra CSV rồi đổi về dạng dài: `participant, clip_code, naturalness, intelligibility, sync` →
`results/mos/mos_responses.csv`, sau đó `python3 NCKH/experiments/mos_analyze.py --responses NCKH/experiments/results/mos/mos_responses.csv`.
Ghi vào `results/mos/NOTES.md`: seed chọn đoạn (42), số người nghe, số người bị loại và lý do. **Không** lưu tên/email, **không** commit video.
