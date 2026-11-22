# Cập nhật bài NCKH sau đợt tối ưu dubbing (15–22/11/2026)

**Viết cho:** session/người sửa bài NCKH (`paper/main.tex`) và người đo lại trên server.

**Mục đích:**
- liệt kê pipeline đã thay đổi gì so với bản dùng để đo trong bài;
- mục nào trong bài phải sửa;
- cách đo lại cho đúng.

**Tài liệu chi tiết từng đợt tối ưu** (trong `docs/improve/performance/`):
- `CaiTien_TocDo_Dubbing.md`: chạy song song, rút gọn theo lô, `atempo`, mức suy nghĩ của Gemini, một lời gọi dịch, `max_chars`, embedding theo lô;
- `CaiTien_NhacNen_Dubbing.md`: nhạc nền, mốc theo từ đầu tiên, câu không có chữ để đọc;
- `SoSanh_GhepChunk.md`: ghép bằng một lệnh FFmpeg, checklist build server;
- `CaiTien_BuocCuoi_TaiLen.md`: bước cuối, dung lượng, đánh thức GPU.

---

## 1. Mốc phiên bản

| Phiên bản | Commit (repo ai-worker) | Ghi chú |
|---|---|---|
| **Bản đo trong bài đã nộp (SSRC, 14/11)** | `e5a8cb7` (nhánh `NCKH`, chứa bản sửa 11/11) | Theo `experiments/reports/REPORT_20261111_Thien.md`. **Nên gắn tag** (ví dụ `nckh-ssrc2026-v1`) để tái lập số liệu cũ |
| Tối ưu đợt 1 | `1750975` (`feat/dubbing`) | TTS song song, rút gọn theo lô, `atempo` thay SSML, log TIMING |
| Tối ưu đợt 2 | `ef5266b` (`feat/dubbing`) | **Một lời gọi dịch** kèm `max_chars`, embedding theo lô, dùng lại kết quả khi chunk chạy lại, sửa lỗi khóa token Azure |
| Nhạc nền và sửa lỗi | `38ed361` (`feat/dubbing`) | Nhạc nền (Demucs/Modal), **mốc đầu câu theo từ đầu tiên**, câu không có chữ để đọc thành khoảng lặng |
| Tối ưu ghép và bước cuối | `cf10f29`, `f2caff6`, `7578395` (`perf/dubbing`) | Ghép bằng một lệnh FFmpeg, bỏ ghép file cuối thừa, đánh thức GPU |

---

## 2. Thay đổi ảnh hưởng tới nội dung bài (PHẢI sửa `main.tex` hoặc đo lại)

| # | Bài báo đang viết | Code hiện tại | Chỗ cần sửa trong `main.tex` |
|---|---|---|---|
| 1 | **Dịch ngữ cảnh hai pha**: lời gọi 1 dịch sát nghĩa, lời gọi 2 biên tập theo ngân sách thời lượng | **Một lời gọi** (`translation.translate_batch`, prompt `_build_dub_prompt`) vừa dịch vừa viết thành lời nói, mỗi câu kèm `budget_sec` và (nếu có) **`max_chars`**. Lời gọi biên tập riêng **đã bị gỡ** (`_build_adapt_prompt` không còn) | Tóm tắt ("dịch hai pha"); danh sách đóng góp (gạch đầu dòng 2); mục **Dịch ngữ cảnh hai pha**; ô "Dịch hai pha bằng LLM" trong Hình 1; định nghĩa V1/V2 ở mục Thực nghiệm |
| 2 | **`max_chars` chưa có** | Sau lượt tạo giọng đầu, worker đo **tốc độ đọc thật (ký tự/giây) của từng giọng**, lưu Redis `dubbing:tts_cps:{voice}` (làm mượt 0,7 cũ và 0,3 mới). Các job sau dịch với `max_chars = cps × thời lượng câu × 1,15`. **Lần đầu dùng một giọng thì chưa có `max_chars`** | Mục dịch: thêm ràng buộc độ dài theo số ký tự ở tầng prompt (gần với isometric MT nhưng không cần huấn luyện). Nêu rõ trạng thái "lần đầu và sau khi đã có số đo" |
| 3 | **Tăng tốc bằng SSML** `<prosody rate>`, tức **gọi lại TTS** đọc nhanh hơn (Thuật toán 1, dòng 12 và 14; câu "dịch vụ TTS sinh lại câu ở tốc độ mới thay vì kéo giãn tín hiệu") | **Tăng tốc ngay trên file đã có bằng FFmpeg `atempo`** (giữ cao độ), hệ số `min(R, 1,3)` (`dubbing_service._synthesize_segments`, `audio_utils.change_tempo`). Không gọi lại TTS | Mục **Điều chỉnh tốc độ đọc thích ứng**, công thức policy (nhánh 2 vẫn là "tăng tốc tối đa 30%" nhưng cơ chế khác), **Thuật toán 1**, trích dẫn `ssml2010` (có thể bỏ). Ghi chú: `atempo` là kéo giãn tín hiệu, có thể ảnh hưởng độ tự nhiên khác với SSML, nên cần đo lại hoặc ghi vào hạn chế |
| 4 | **Rút gọn từng câu**, mỗi câu một lời gọi LLM, lặp tối đa M = 2 | **Rút gọn theo lô**: mỗi vòng **một lời gọi** cho mọi câu có R > 1,3 và khung ≥ 2 s, mỗi câu kèm `max_chars ≈ len × 1,25 × T_orig / T_tts`. Vẫn M = 2, T_min = 2 s, ngưỡng 1,3 và 1,0. Lời gọi rút gọn lỗi thì chuyển sang tăng tốc tối đa | Thuật toán 1 (vòng `while`, viết theo lô), số lời gọi LLM ở Bảng 2 (286 lời gọi giờ sẽ ít hơn nhiều) |
| 5 | Mốc đầu câu `b_i` là mốc đầu đoạn của Whisper | `b_i` = **thời điểm từ đầu tiên** trong câu (`groq_asr._first_word_start`, dùng mốc theo từ của Groq). Sửa lỗi lời lồng tiếng đè lên nhạc intro: câu 1 bài Crash Course từ 0,0 s thành 3,16 s | Mục Nhận dạng giọng nói (định nghĩa `b_i`). Công thức `eq:onset` **giữ nguyên**. Có thể làm thay đổi độ trễ theo trục thời gian (Bảng 3), nên cần đo lại |
| 6 | Mô hình LLM: Gemini 3.5 Flash | Vẫn Gemini 3.5 Flash nhưng **mức suy nghĩ `minimal`** (`DUBBING_THINKING_LEVEL`) | Bảng 1 (tham số): thêm dòng mức suy nghĩ |
| 7 | Thời gian xử lý khoảng **110 s mỗi phút video** (Bảng 4, hạn chế (iii), phần Vận hành) | Lần lồng tiếng đầu khoảng **12 s mỗi phút** (job 44: bài 9 phút 13 giây xong trong 113,8 s, có nhạc nền); ngôn ngữ sau khoảng 5 s mỗi phút | Bảng 4, đoạn "Vận hành trên hệ thống thật", hạn chế (iii). **Đo lại trên server** |

**Thay đổi nhỏ**, ghi vào bài nếu cần, không bắt buộc:
- Câu chỉ có dấu câu (Whisper hay trả `"."` ở đoạn nhạc) được thay bằng 0,1 s im lặng thay vì gửi TTS.
- Câu bị Gemini bỏ sót khi dịch được dịch lại riêng; vẫn thiếu thì giữ câu gốc.
- Ô "Ghép câu theo khoảng lặng gốc" trong Hình 1 **đã lệch ngay trong bài hiện tại** (phần chữ mô tả cách xếp theo mốc tuyệt đối), nên đổi thành "Xếp câu theo mốc tuyệt đối → âm thanh của đoạn".

## 3. Thay đổi KHÔNG ảnh hưởng nội dung bài (không cần sửa, hoặc chỉ nhắc ở phần Triển khai hay Hướng phát triển)

- **Phân đoạn theo lớp** giữ nguyên: đoạn 600 s xử lý tuần tự, báo tiến độ từng đoạn, thử lại 3 lần, lỗi thì giữ audio gốc, bỏ qua đoạn có lời thoại dưới 10%.
- **Xếp theo mốc tuyệt đối** (`eq:onset`), tăng tốc cả đoạn tối đa ×1,15, khớp đúng độ dài đoạn: **thuật toán giữ nguyên**. Chỉ đổi **cách cài đặt** (một lệnh FFmpeg thay cho pydub); đã kiểm chứng cho kết quả tương đương, xem `SoSanh_GhepChunk.md`.
- Nối các đoạn thành file cuối bằng FFmpeg chép thẳng: dư khoảng 30 ms ở mỗi chỗ nối. Bài đo bài tối đa 15 phút (1 chỗ nối), nên câu "chênh không quá 0,1 giây" vẫn đúng.
- Chống trùng, dùng lại bản lồng tiếng và bản ký âm, trình phát kép: giữ nguyên.
- **Nhạc nền** (tách giọng và nhạc bằng Demucs trên GPU Modal, trộn giữ tỉ lệ gốc) là tính năng mới **không có trong bài**. Có thể nhắc ở Triển khai hoặc Hướng phát triển. **Nên tắt khi đo lại** để số liệu so được với bài cũ (mục 4).
- Embedding theo lô, đánh thức GPU, dung lượng file, bỏ ghép file cuối thừa: chỉ là tối ưu thời gian.
- **Đề xuất còn mở**, chưa làm và không ảnh hưởng bài: tách nhạc theo đoạn và song song; không tải lại video gốc cho ngôn ngữ thứ 2; đưa embedding ra chạy nền.
  - **Ngoại lệ:** **đổi model Gemini** (ví dụ Flash-Lite) **sẽ ảnh hưởng** độ dài và chất lượng bản dịch. **Không đổi model trước khi đo xong.**

## 4. Kế hoạch đo lại

**Bước 0: chuẩn bị code**
1. Merge `perf/dubbing` vào `develop` (nhánh này đã chứa `feat/dubbing`), rồi nhánh `NCKH` merge `develop`.
2. Gắn tag cho bản cũ: `git tag nckh-ssrc2026-v1 e5a8cb7 && git push origin nckh-ssrc2026-v1`.
3. **Sửa `experiments/run_experiment.py`. Hiện chạy LỖI trên code mới:**
   - `_translate_both_phases` gọi `translation._build_adapt_prompt`, hàm này **không còn**.
   - V3 tăng tốc bằng tham số `rate=` của `azure_tts.synthesize`, tức SSML, **không còn là cơ chế của pipeline**.
   - Bộ đếm vá `translation.resummarize`, nhưng pipeline giờ gọi `translation.resummarize_batch`, nên phải vá hàm này (hoặc đếm thẳng `gemini.generate`).
4. **Định nghĩa lại các phương án.** Cần chốt với Sang; đề xuất:
   - **V1**: dịch không ràng buộc độ dài (`_build_direct_prompt`, vẫn còn), tốc độ mặc định.
   - **V2**: dịch theo ngân sách thời lượng (`translate_batch` với `max_chars=None`), tốc độ mặc định.
   - **V3**: V2 cộng `max_chars` (từ tốc độ đọc đo được) cộng tăng tốc `atempo` ≤ ×1,3, **không** rút gọn.
   - **V4**: pipeline đầy đủ hiện tại (`dubbing_service._synthesize_segments`: rút gọn theo lô, `atempo`).
   - Muốn so với bài cũ thì giữ thêm một dòng "bài cũ (`e5a8cb7`)" bằng số liệu đã có. **Không trộn** số liệu cũ và mới trong cùng một phương án.

**Bước 1: chuẩn bị server** (người giữ server)
1. Build lại theo mục 6 của `docs/improve/performance/SoSanh_GhepChunk.md`.
2. **Tắt nhạc nền khi đo:** đặt `BGM_SEPARATION=` (để trống), rồi `docker compose up -d --force-recreate ai-worker`.
3. **Tốc độ đọc của giọng:** ghi lại hoặc xóa khóa Redis `dubbing:tts_cps:vi-VN-*` trước khi đo, vì lần đầu của một giọng không có `max_chars`. Đề xuất chạy V4 **hai lần**:
   - lần 1: chưa có số đo;
   - lần 2: đã có số đo.

   Báo cáo cả hai, hoặc chọn lần 2 làm kết quả chính và ghi rõ.
4. Giữ nguyên: `GEMINI_MODEL` (3.5 Flash), `DUBBING_THINKING_LEVEL=minimal`, `TTS_CONCURRENCY` (mặc định 16), `TIMELINE_ENGINE=ffmpeg`.
5. Ghi commit đang chạy, giá trị `.env` liên quan (không ghi key) và trạng thái các khóa `tts_cps` vào NOTES của đợt đo.

**Bước 2: đo**
- **Cùng 4 bài** như bài cũ (xem `experiments/videos.json`), để so được.
- **Độ khớp thời lượng** (Bảng 2): Δ trung bình, % câu tràn, % R > 1,3, số lời gọi LLM và TTS, chạy bằng `run_experiment.py` đã sửa.
- **Độ trễ theo trục thời gian** (Bảng 3): `check_full_length.py` và `drift_analysis.py` trên âm thanh mới. Lưu ý: mốc `b_i` giờ theo từ đầu tiên.
- **Vận hành** (Bảng 4): lồng tiếng thật 4 bài qua web, lấy thời gian từ `ai_jobs` và `audio_chunks`, cùng dòng log `TIMING`. Xóa bản lồng tiếng và transcript cũ của các bài trước khi chạy, để có lần đầu (có bước nhận dạng giọng nói).
- **Độ bảo toàn ý** (L4): câu rút gọn đã khác, nên **chấm lại 50 câu** (2 người, cùng quy trình và hạt giống cố định).
- Nếu chạy lại MOS: chấm trên audio của bản mới.

**Bước 3: sửa `main.tex`** theo mục 2, thay số liệu mới.
- Nếu không kịp đo lại, **phương án tối thiểu**: giữ mô tả và số liệu bản `e5a8cb7`, thêm một đoạn ở Triển khai hoặc Thảo luận rằng sau đánh giá, hệ thống được tối ưu tốc độ (gộp lời gọi dịch, `atempo`, rút gọn theo lô; khoảng 12 s mỗi phút video), **ghi rõ các thay đổi này không nằm trong phần đánh giá**.
- **Không** mô tả thuật toán mới đi kèm số liệu cũ.
