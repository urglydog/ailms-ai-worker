# So sánh 2 cách ghép câu thành chunk: pydub (cũ) và 1 lệnh FFmpeg (mới), 22/11/2026

Nhánh: `perf/timeline-ffmpeg` (tách từ `feat/dubbing`). Tiếp theo [CaiTien_TocDo_Dubbing.md](CaiTien_TocDo_Dubbing.md) và [CaiTien_NhacNen_Dubbing.md](CaiTien_NhacNen_Dubbing.md).

## 1. Bước "ghép" làm gì

Sau khi tạo giọng, mỗi câu là một file MP3. Bước ghép (`audio_utils.place_on_timeline`) dựng thành **một file audio cho cả chunk** theo quy tắc BR-CHUNK-05:
1. Đặt mỗi câu tại **mốc tuyệt đối** của nó (`plan_onsets`). Câu sau không bao giờ chồng lên câu trước; câu bị lùi sẽ quay về đúng mốc ngay khi gặp khoảng lặng đủ dài.
2. Nếu cả chunk dài hơn khung thì **tăng tốc cả đoạn** (FFmpeg `atempo`, tối đa ×1,15).
3. **Cắt hoặc đệm** cho đúng độ dài chunk, để chunk sau bắt đầu đúng giờ.

## 2. Hai cách

| | Cách cũ: `place_on_timeline_pydub` | Cách mới: `place_on_timeline_ffmpeg` |
|---|---|---|
| Giải mã câu | Mỗi câu pydub mở **1 tiến trình FFmpeg**, chạy lần lượt (khoảng 0,1–0,2 s mỗi câu) | **Một tiến trình FFmpeg** đọc tất cả câu |
| Dựng chunk | Nối dần trong Python; mỗi lần nối sao chép lại cả đoạn đã có | Bộ lọc `concat` nối [lặng, câu, lặng, câu, …] |
| Tăng tốc khi tràn | Xuất WAV, chạy FFmpeg `atempo`, đọc lại | `atempo` trong cùng lệnh |
| Cắt hoặc đệm, mã hóa MP3 | Thêm 1 lượt FFmpeg | `apad` + `atrim` trong cùng lệnh |
| Số tiến trình FFmpeg | khoảng **số câu + 2** | **1** |

**Không đổi:** cách tính mốc (cùng hàm `plan_onsets`), hệ số tăng tốc tối đa, độ dài đầu ra, và các chỉ số `TimelineResult` (`raw_length_sec`, `max_delay_sec`, `tempo_applied`).

**Hai điểm kỹ thuật phải xử lý:**
1. **Độ dài câu:** không lấy từ header MP3. `ffprobe` đọc **dư khoảng 35–45 ms mỗi câu** vì tính cả phần đệm của bộ mã hóa; qua 190 câu sẽ lệch dồn vài giây. Lỗi này được test `test_ffmpeg_engine_places_sentences_where_pydub_does` phát hiện. Cách mới dùng độ dài chính xác code đã đo sẵn lúc tạo giọng (`SynthesisResult.duration_sec`).
2. **Không để sai số dồn:** mỗi câu được `apad` và `atrim` về **đúng ô thời gian** của nó. Sai số nhỏ của từng câu không ảnh hưởng tới vị trí các câu sau.

**An toàn:** cách mới lỗi thì **tự quay về cách cũ** và ghi cảnh báo `Ghep bang 1 lenh FFmpeg that bai`. Chọn cách ghép bằng `TIMELINE_ENGINE=ffmpeg|pydub`, mặc định `ffmpeg`.

## 3. Đo trên dữ liệu giả lập giống thật

Chạy `scripts/bench_timeline.py`, trung bình 3 lần, trong container worker.
- Các câu cắt từ bài TED-Ed, mỗi câu dài 1,5–4,5 s, mã hóa giống Azure (MP3 16 kHz mono 32 kbps).
- Khoảng 20% câu đã tăng tốc bằng `change_tempo`, có cả câu tràn sang câu sau.

| Cỡ | Cách cũ | **Cách mới** | Nhanh hơn |
|---|---|---|---|
| 63 câu / 376 s (bài 6 phút) | 7,04 s | **0,93 s** | khoảng 7,6 lần |
| 122 câu / 566 s (bài 9,4 phút) | 14,51 s | **1,48 s** | khoảng 9,8 lần |
| 190 câu / 600 s (chunk 10 phút đầy) | 20,75 s | **1,86 s** | khoảng 11 lần |
| 190 câu / 480 s (chunk tràn, tăng tốc ×1,15) | 21,52 s | **1,60 s** | khoảng 13 lần |

**Kết quả có giống nhau không:**

| Cỡ | Độ dài (cũ / mới) | Câu lệch mốc nhiều nhất (cũ / mới) | Tương quan đường bao âm lượng |
|---|---|---|---|
| 63 câu | 376,000 / 376,000 s | 0 / 0 ms | 0,9988 |
| 122 câu | 566,000 / 566,000 s | 30 / 15 ms | 0,9987 |
| 190 câu | 600,000 / 600,000 s | 10 / 0 ms | 0,9976 |
| 190 câu, tràn | 480,000 / 480,000 s | 295 / 300 ms (*) | 0,9784 |

- Hai chỉ số trễ tối đa (`max_delay_sec`) và hệ số tăng tốc (`tempo_applied`) trùng nhau ở mọi cỡ.
- (*) Ở ca tràn, script kiểm tra so với mốc **trước khi** tăng tốc nên cả hai cách đều lệch khoảng 300 ms như nhau. Đây là giới hạn của script, không phải lỗi đặt câu.
- Tương quan 0,978 ở ca này vì hai cách chạy `atempo` ở hai định dạng mẫu khác nhau (WAV 16-bit so với float). Khác biệt rất nhỏ.
- **Vì sao so đường bao âm lượng, không so dạng sóng:** mã hóa MP3 lại làm lệch pha từng mẫu. Hai file nghe giống hệt nhau vẫn có tương quan dạng sóng chỉ khoảng 0,7–0,8, nên chỉ số đó không phản ánh đúng.

## 4. Đo bằng job thật

Cùng bài 3462 (lec01, 9 phút 26 giây, **122 câu**):

| Job | Cách ghép | Bước `ghep` trong log TIMING |
|---|---|---|
| 35 (21/11, tiếng Việt) | pydub | **24,4 s** (có kèm khoảng 1–2 s tạo embedding cho Tutor) |
| 42 (22/11, tiếng Nhật) | **ffmpeg** | **1,4 s** |

Dòng TIMING của job 42:
```
asr=0.0s dich=8.8s tts=13.5s ghep=1.4s nhac=65.2s upload=18.8s tong=107.8s
```
- Người dùng thấy job hoàn tất sau khoảng **125 s**.
- Thời gian còn lại là chờ tách nhạc lần đầu trên GPU (bài này chưa có nhạc trên B2). Worker sau đó chạy tiếp khoảng 2,5 phút để tải nhạc lên B2, chạy nền và không ảnh hưởng người xem.

**Ước tính cho chunk 10 phút đầy (khoảng 190 câu):** bước ghép từ khoảng 30–40 s xuống còn khoảng **2–3 s**, tức mỗi chunk nhanh hơn khoảng 30 s.

## 5. Kết luận

- Nhanh hơn **8–17 lần** ở bước ghép, kết quả tương đương cách cũ, logic cốt lõi giữ nguyên, và có tự quay về cách cũ khi lỗi. **Đề xuất đưa vào luồng chính** với `TIMELINE_ENGINE=ffmpeg`.
- **Nhược điểm đã biết:**
  1. ~~Phụ thuộc phiên bản FFmpeg~~ **(đã xử lý)**: đồ thị bộ lọc giờ được **truyền thẳng trên dòng lệnh** (`-filter_complex`), nên chạy được cả FFmpeg 5.x (Debian 12) lẫn 7.x (Debian 13). Image dùng `python:3.11-slim` không ghim bản Debian, nên server có thể đang chạy bản cũ hơn máy local.
     - Chunk 10 phút khoảng 190 câu thì đồ thị chỉ khoảng 25 KB, dưới xa giới hạn 128 KB cho một đối số dòng lệnh của Linux. Đo lại 190 câu: 2,9 s, độ dài đúng 600,000 s.
     - Đồ thị vượt 100 000 ký tự thì ghi ra file và dùng `-filter_complex_script`, có từ bản 5.x tới 7.x. Có test riêng cho nhánh này.
  2. ~~Cần độ dài câu từ caller~~ **(đã xử lý)**: luồng lồng tiếng (`dubbing_service.py`) truyền sẵn `durations_sec` lấy từ kết quả tạo giọng. Chỉ còn 2 script NCKH (`NCKH/experiments/check_full_length.py`, `mos_make_clips.py`) gọi mà không truyền; khi đó hàm tự giải mã để đo, chậm hơn nhưng vẫn đúng. Muốn tái lập đúng số liệu bài báo thì chạy các script đó với `TIMELINE_ENGINE=pydub`.
- **Kiểm thử:** `tests/test_timeline.py` chạy cho **cả hai cách** (đệm đủ độ dài, tăng tốc khi tràn, câu đặt đúng chỗ như cách cũ, tự quay về khi lỗi). Toàn bộ: **129 passed**, 6 skipped.

## 6. Build lại server lên bản mới nhất (checklist cho người hoặc AI thực hiện)

Mục này **gộp cho mọi đợt tối ưu dubbing**: tốc độ, nhạc nền và cách ghép mới. Chỉ **ai-worker** thay đổi, gồm 3 service build từ thư mục `../ai-worker` là `ai-api`, `ai-worker` và `ai-beat`. **be và fe không cần build lại.**

> **Vì sao nên build lại hẳn, kể cả khi code đã chạy:**
> - Image worker build từ `python:3.11-slim`, **không ghim** bản Debian. Image build từ trước có thể vẫn là Debian 12 với FFmpeg 5.1; build mới sẽ ra Debian 13 với FFmpeg 7.1.
> - Từ commit `f2caff6`, cách ghép mới **chạy được cả hai bản FFmpeg**, nên không build lại thì cũng không lỗi.
> - Build lại vẫn nên làm để: (1) server và máy local cùng một môi trường; (2) cài thư viện `modal` mới thêm trong `requirements-app.txt`. Thiếu `modal` thì tách nhạc nền **không chạy**: job vẫn lồng tiếng nhưng không có nhạc.

**Bước 0: chuẩn bị.**
- Các nhánh `feat/dubbing` và `perf/timeline-ffmpeg` của ai-worker đã được merge vào nhánh đang deploy, ví dụ `develop`, rồi `main`.
- Tìm thư mục chứa `docker-compose.yml`, thường là `project/be`.
- Ghi lại phiên bản đang chạy để so sánh sau:
```bash
docker exec lms_ai_worker sh -c "ffmpeg -version | head -1; cat /etc/debian_version"
```

**Bước 1: lấy code mới.** Trong `project/ai-worker`:
```bash
git pull
grep -c "place_on_timeline_ffmpeg" app/audio_utils.py
```
Lệnh thứ hai phải in ra một số lớn hơn 0.

**Bước 2: cập nhật `project/ai-worker/.env`.**
- Làm như mục 6, bước 1 của [CaiTien_NhacNen_Dubbing.md](CaiTien_NhacNen_Dubbing.md): `BGM_SEPARATION=modal`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `DUBBING_THINKING_LEVEL=minimal`.
- Có thể thêm `TIMELINE_ENGINE=ffmpeg`. Đây đã là mặc định nên không bắt buộc.
- Không commit `.env`, không in token ra log.

**Bước 3: build lại từ base image mới nhất.** Trong thư mục chứa `docker-compose.yml`:
```bash
docker compose build --pull --no-cache ai-api ai-worker ai-beat
docker compose up -d --force-recreate ai-api ai-worker ai-beat
```
- `--pull`: tải bản `python:3.11-slim` mới nhất (Debian 13).
- `--no-cache`: cài lại toàn bộ, gồm FFmpeg mới qua `apt-get` và thư viện `modal`. Bỏ cờ này thì Docker có thể dùng lại lớp cài FFmpeg cũ.
- `--force-recreate`: tạo lại container để nạp image mới và `.env` mới. Lệnh `restart` **không** nạp lại `.env`.
- Build mất vài phút. Trong lúc build, job lồng tiếng đang chạy vẫn tiếp tục; container chỉ dừng khoảng vài giây ở bước `up`.
- Có job đang chạy dở thì nên chờ nó xong rồi mới chạy bước `up`, để job không bị ngắt giữa chừng.

**Bước 4: kiểm tra.**
```bash
docker exec lms_ai_worker sh -c "ffmpeg -version | head -1; cat /etc/debian_version"
docker exec lms_ai_worker python -c "from app.config import settings; print(settings.timeline_engine, settings.bgm_separation)"
docker exec lms_ai_worker python -c "import modal; modal.Function.from_name('lms-demucs','separate').hydrate(); print('modal ok')"
```

| Lệnh | Kết quả mong đợi |
|---|---|
| 1 | `ffmpeg version 7.x` và `13.x`. Nếu vẫn là 5.x thì chưa chạy `--pull`, nhưng vẫn chạy được. |
| 2 | `ffmpeg modal` |
| 3 | `modal ok` |

**Bước 5: chạy thử một bài, rồi xem log.**
```bash
docker logs -f lms_ai_worker | grep -E "TIMING|BGM|Ghep bang 1 lenh"
```
- Dòng `TIMING ... ghep=...s` phải **nhỏ**: khoảng 1–3 s cho mỗi chunk. Trước đây là 10–40 s.
- **Không** được có dòng `Ghep bang 1 lenh FFmpeg that bai`. Nếu có, nghĩa là đã tự quay về cách cũ; gửi lại đoạn log đó để xử lý.
- Có các dòng `BGM tach nhac xong` (hoặc `BGM dung lai nhac da tach tren B2`) và `BGM tron nhac chunk ...`.

**Bước 6: dọn image cũ (tùy chọn, giải phóng dung lượng đĩa).**
```bash
docker image prune -f
```

**Quay lại cách cũ nếu cần:**
- Ghép lại bằng pydub: đặt `TIMELINE_ENGINE=pydub` trong `.env`, rồi chạy `docker compose up -d --force-recreate ai-worker`.
- Tắt nhạc nền: để trống `BGM_SEPARATION`, rồi chạy lệnh tương tự.
- Không cần build lại cho cả hai trường hợp.
