# Giữ nhạc nền khi lồng tiếng và các sửa lỗi đi kèm (21/11/2026)

Tiếp theo [CaiTien_TocDo_Dubbing.md](CaiTien_TocDo_Dubbing.md). Hướng dẫn cấu hình Modal ở [HuongDan_Modal_TachNhacNen.md](HuongDan_Modal_TachNhacNen.md).

## 1. Vấn đề

- **Mất nhạc nền:** video phát ở chế độ tắt tiếng, người học chỉ nghe file MP3 lồng tiếng. File này dựng từ các câu đọc đặt trên nền im lặng, nên nhạc intro, nhạc nền dưới lời nói và hiệu ứng âm thanh của video gốc đều mất.
- **Lời lồng tiếng đè lên nhạc intro:** Whisper hay gộp khoảng không có lời ở đầu vào câu đầu tiên. Ví dụ bài Crash Course: câu 1 ghi bắt đầu ở 0,0 s, trong khi người nói chỉ bắt đầu ở khoảng 3,2 s.
- **Chunk hỏng vì câu không có chữ để đọc:** Whisper trả câu chỉ có dấu `"."` ở đoạn nhạc. Azure trả về file 0 byte, FFmpeg không đọc được, và chunk hỏng sau cả 3 lần thử.

## 2. Giải pháp

### 2.1. Tách giọng và nhạc bằng Demucs trên GPU của Modal

**Luồng xử lý** (`app/services/background_music.py`, `modal_apps/demucs_separator.py`):
1. Ngay sau khi tải audio gốc, worker gửi một file MP3 lên hàm Demucs (`htdemucs`, tách 2 phần) chạy trên **GPU T4** của Modal.
2. Việc này chạy **song song** với nhận dạng, dịch và tạo giọng.
3. Nhận về 2 file: **nhạc nền** (`no_vocals`) và **giọng gốc** (`vocals`).

**Vì sao chọn Modal:**
- Tính phí theo giây GPU và có 30 USD miễn phí mỗi tháng.
- Image của worker không phải cài PyTorch hay Demucs, nên không nặng thêm vài GB và server không tốn CPU.
- So sánh với các lựa chọn khác:
  - Azure for Students không cấp được GPU, vì hạn mức GPU bằng 0.
  - Google Cloud Run GPU không có gói miễn phí và tốn công đóng gói hơn.
  - Replicate phải nạp tiền trước.

### 2.2. Trộn giữ đúng tỉ lệ giọng và nhạc của bản gốc

- **Nhạc giữ nguyên âm lượng gốc** (`BGM_MUSIC_VOLUME=1.0`), vì người làm video đã cân sẵn nhạc so với giọng.
- **Giọng lồng tiếng được chỉnh to bằng giọng gốc:**
  - Đo độ to tích hợp (EBU R128, bộ lọc `ebur128` của FFmpeg) của giọng gốc đã tách và của bản lồng tiếng **trong đúng chunk đó**.
  - Cộng hoặc trừ số dB chênh lệch vào giọng lồng tiếng, giới hạn trong ±12 dB.
  - Số đo thực tế: giọng Azure thường to hơn giọng gốc khoảng 1,8–2,5 dB.
- **Không tự hạ nhạc khi có lời** theo mặc định (`BGM_DUCKING=false`). Chỉ bật nếu nghe thấy giọng gốc còn sót trong phần nhạc tách ra.
- Có thêm bộ giới hạn `alimiter` để không bị rè khi giọng và nhạc cộng lại quá to.

### 2.3. Tách một lần cho mỗi bài, lưu lên B2

- Nhạc và giọng gốc đã tách được lưu tại `bgm/{id bài}/{sha1(link video)[:12]}/music.mp3` và `vocals.mp3`.
- Lồng tiếng bài đó sang ngôn ngữ khác sẽ tải về từ B2, **không gọi GPU nữa**.
- Khóa lưu có kèm mã của link video, nên đổi video thì không dùng nhầm nhạc cũ.
- Việc tải lên B2 **chạy nền**, không bắt bước trộn phải chờ. Job chỉ đợi tải lên xong trước khi xóa thư mục tạm.

### 2.4. Gọn bước trộn

- **Trước:** 5 lượt FFmpeg cho mỗi chunk (cắt nhạc ra MP3, cắt giọng gốc ra MP3, 2 lần đo bằng `loudnorm`, rồi trộn).
- **Sau:** 3 lượt, không có file trung gian. Hai phép đo `ebur128` chạy song song, cắt đoạn ngay lúc đọc file (`-ss/-to`), rồi 1 lượt trộn.
- **Kết quả:** 22,4 s xuống **5,3 s** cho bài 6 phút.

### 2.5. Các sửa lỗi đi kèm

| Lỗi | Sửa |
|---|---|
| Lời lồng tiếng đè lên nhạc intro | `groq_asr._first_word_start`: mốc bắt đầu câu lấy theo **từ đầu tiên** (Groq đã trả mốc theo từ). Câu 1 bài Crash Course từ 0,0 s thành 3,16 s. |
| Câu chỉ có dấu câu làm hỏng chunk | Câu không có chữ cái hay chữ số nào thì không gửi Azure, thay bằng 0,1 s im lặng. Nếu Azure vẫn trả file rỗng thì câu đó cũng được thay bằng im lặng. |

## 3. Số đo (bài TED-Ed 6 phút 16 giây, 63 câu)

| Lần chạy | Tách nhạc | Lồng tiếng phải chờ nhạc | Đo độ to và trộn | **Cả job** |
|---|---|---|---|---|
| Tách bằng CPU của Modal (job 36) | 137 s | 103 s | 8,5 s | 180 s |
| **Lần đầu, GPU T4** (job 38) | 66 s | 29 s | 22,4 s | **118 s** |
| **Ngôn ngữ thứ 2, dùng lại từ B2** (job 41) | **5,9 s** | **0 s** | **5,3 s** | **63 s** |

**Ghi chú:**
- Job 41 dùng lại transcript gốc nên không có bước nhận dạng.
- Job 40 (245 s) bị chờ tải lên B2 trên mạng chậm. Lỗi này đã sửa nhưng chưa đo lại lần đầu của một bài khác.

**So sánh T4 và L4** (cùng file, Modal):

| GPU | Giá | Demucs | Tổng, máy chạy sẵn | Tổng, khởi động nguội |
|---|---|---|---|---|
| **T4** | 0,000164 USD/giây | 53–57 s | 60,5 s | 70,6 s |
| L4 | 0,000222 USD/giây | 45–47 s | 49,5 s | **584,7 s** (chờ cấp GPU) |

- **Chọn T4:** phí mỗi bài gần như ngang L4 (khoảng 1–2 cent, ước tính), và không phải chờ cấp GPU.
- Phí GPU tính **một lần cho mỗi bài**, không nhân theo số ngôn ngữ.

## 4. Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BGM_SEPARATION` | rỗng (tắt) | `modal` để bật tách nhạc |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | | Token của tài khoản Modal đã deploy hàm `lms-demucs` |
| `BGM_MODAL_APP` | `lms-demucs` | Tên app trên Modal |
| `BGM_MUSIC_VOLUME` | 1.0 | Âm lượng nhạc nền |
| `BGM_DUCKING` | false | Tự hạ nhạc khi có lời |
| `BGM_WAIT_TIMEOUT_SEC` | 600 | Chờ tách nhạc tối đa; quá hạn thì chunk đó không có nhạc |

Mọi lỗi ở bước tách hoặc trộn nhạc chỉ được ghi cảnh báo. Job **vẫn lồng tiếng bình thường**, chỉ không có nhạc nền.

## 5. Kiểm thử

- `tests/test_background_music.py`:
  - tắt theo mặc định;
  - lỗi thì giữ bản lồng tiếng;
  - khớp độ to và giữ nhạc ở mức 1,0;
  - tự hạ nhạc là tùy chọn;
  - dùng lại nhạc từ B2 thì không gọi GPU;
  - trộn bằng 1 lượt FFmpeg;
  - tải lên B2 không chặn bước trộn.
- `tests/test_groq_word_onsets.py`: mốc câu lấy theo từ đầu tiên.
- `tests/test_adaptive_rate.py`: câu chỉ có dấu câu, và Azure trả audio rỗng.

## 6. Việc có thể làm tiếp

- **Bỏ qua tách nhạc cho bài không có nhạc nền:** kiểm tra năng lượng âm thanh trong các khoảng không có lời, không có nhạc thì không gọi GPU.
- **Giảm thời gian Modal giữ máy sau mỗi lần gọi:** trang giá nhắc có thể bị tính phí khoảng 60 s máy chờ; điểm này chưa kiểm chứng. Mỗi job chỉ gọi tách nhạc một lần nên không cần giữ máy lâu.
- **Đo lại lần lồng tiếng đầu tiên** sau khi đã sửa việc chờ tải lên B2.
