# Hướng dẫn tiếp tục bài báo NCKH (SSRC-II'2026)

> File này dùng làm **context cho AI (Claude) của thành viên trong nhóm**. Đưa nguyên file cho Claude
> và nói: *"Đọc NCKH/HUONG_DAN_NHOM.md rồi tiếp tục công việc ở mục 6."*
> Claude: đọc hết file này trước khi làm bất cứ việc gì. Trả lời bằng **tiếng Việt**.
>
> **Cập nhật mới nhất: mục 9 – Kế hoạch đo đợt 2 (10/11/2026).** Ai đã đọc các mục 1–8 thì đọc tiếp từ mục 9.

---

## 1. Bối cảnh

| Mục | Nội dung |
|---|---|
| Hội nghị | SSRC-II'2026, Khoa CNTT, ĐH Công nghiệp TP.HCM — https://ssrc.fit.iuh.edu.vn/conf/announcement/view/4 |
| Hạn | **15/11/2026 nộp bài** · 22/11 có kết quả phản biện · 04/12 nộp bản chính thức · 11/12 hội nghị |
| Chủ đề nộp | **Chủ đề 4 – Khoa học máy tính & Khoa học dữ liệu** (mục *Speech recognition*, *NLP/Language Model*, *Applications of ML – edtech*). Dự phòng: Chủ đề 2 (*Web-based Education Systems*). |
| Tên bài | *Pipeline lồng tiếng tự động cho video bài giảng trực tuyến với cơ chế điều chỉnh tốc độ đọc thích ứng* |
| Ngôn ngữ | Tiếng Việt (có thể dịch sang tiếng Anh sau khi bản Việt ổn) |
| Tác giả | Nguyễn Hữu Sang, Nguyễn Chí Thiện; GVHD: ThS. Nguyễn Thị Hoàng Khánh (email: bổ sung sau) |
| Hệ thống gốc | Khóa luận "AI-Powered LMS" (nền tảng **LinguaLearn**). Bài báo chỉ trình bày **phần pipeline lồng tiếng AI**, không kể lại toàn bộ LMS. |

## 2. Cấu trúc thư mục

```
NCKH/                         (nằm trong repo ai-worker: project/ai-worker/NCKH)
├── HUONG_DAN_NHOM.md         ← file này
├── format/                   template gốc của hội nghị (KHÔNG sửa)
│   ├── SSRC_template/        main.tex mẫu (IEEEtran + vietnam), tns1.png, tns2.png
│   ├── SSRC_template.pdf
│   └── SSRC_Word_Template.docx
├── resources/
│   └── AI-Powered_LMS.docx   báo cáo khóa luận (nguồn nội dung, chỉ đọc)
├── paper/                    ← MÃ NGUỒN BÀI BÁO
│   ├── main.tex              toàn bộ bài báo (1 file)
│   ├── main.pdf              bản biên dịch gần nhất
│   └── SSRC_LongTieng_overleaf.zip   (đóng gói để upload Overleaf)
└── experiments/              ← SCRIPT ĐO SỐ LIỆU
    ├── run_experiment.py     chạy 4 phương án V1–V4, ghi CSV từng câu
    ├── analyze.py            tổng hợp CSV -> bảng số liệu + dòng LaTeX + biểu đồ
    ├── server_job_stats.py   đọc số liệu job thật trên server (CHỈ ĐỌC)
    ├── server_job_stats.sql  các câu SELECT dùng cho script trên
    ├── videos.example.json   mẫu danh sách video thử nghiệm
    └── results/              kết quả đo (mỗi lần chạy 1 thư mục)
```

## 3. Quy tắc bắt buộc

1. **Định dạng**: giữ nguyên preamble của template SSRC (`\documentclass{IEEEtran}`, `\usepackage[utf8]{vietnam}`,
   `cite`, `amsmath`, `graphicx`…). Chỉ được thêm gói không đổi layout (đã thêm: `xcolor`, `tikz`, `algorithm`,
   `algpseudocode`). Không đổi font, lề, cỡ chữ, số cột.
2. Yêu cầu template: tóm tắt **150–250 từ, 1 đoạn**, không viết tắt, không trích dẫn, không công thức;
   Index Terms 3–6 từ khóa theo **thứ tự chữ cái**; tài liệu tham khảo theo **chuẩn IEEE** (`thebibliography`
   trong main.tex, không dùng file .bib); hình/bảng phải được nhắc trong văn bản; bảng là LaTeX, không chèn ảnh bảng.
3. **Số liệu kỹ thuật phải lấy từ code thật** (repo `project/ai-worker`, `project/be`), không lấy từ tài liệu cũ.
   Báo cáo khóa luận có chỗ đã lỗi thời (xem mục 5).
4. Chỗ chưa có dữ liệu đánh dấu bằng `\todo{...}` (hiện chữ đỏ). **Xóa hết `\todo` trước khi nộp.**
5. **Server**: chỉ được ĐỌC (SELECT). Không tạo job, không sửa/xóa dữ liệu, không restart dịch vụ.
   Dữ liệu trên server thuộc bạn trong nhóm — hỏi Sang trước khi làm gì ngoài việc đọc.
6. Không commit mật khẩu, API key, chuỗi kết nối DB. Dùng biến môi trường.
7. Chỉ commit/push khi người dùng yêu cầu.
8. Tài liệu tham khảo phải **có thật**; không bịa số trang/năm. Không chắc thì hỏi lại hoặc bỏ.
9. *(10/11)* Người đo **không sửa `paper/main.tex`**; đầu ra là REPORT theo mục 9.6 để nhóm kiểm tra lại.

## 4. Biên dịch bài báo

**Overleaf**: New Project → Upload Project → chọn `paper/SSRC_LongTieng_overleaf.zip` (hoặc tạo zip mới chỉ chứa `main.tex`) → Recompile.

**Máy local (MiKTeX, Windows)** — đứng ở thư mục `NCKH/paper`, chạy 2 lần để cập nhật tham chiếu:
```bash
pdflatex -interaction=nonstopmode -output-directory=build main.tex
pdflatex -interaction=nonstopmode -output-directory=build main.tex
```
Rồi copy `build/main.pdf` ra `paper/main.pdf`. Kiểm tra log: không có dòng `!` (lỗi), không có `Overfull \hbox` lớn,
không có `undefined` reference.

## 5. Sự thật kỹ thuật (đã đối chiếu với code)

| Thành phần | Giá trị thật | Nguồn trong code |
|---|---|---|
| Chia đoạn | Cố định **10 phút** (600 s), đoạn cuối chứa phần dư | `ai-worker/app/services/dubbing_service.py` `split_into_chunks`, `config.chunk_minutes` |
| Retry | **3 lần**/đoạn, backoff mũ; hết retry giữ **audio gốc** riêng đoạn đó | `_process_chunk_with_retry`, `config.max_retry` |
| Bỏ qua đoạn không lời | lời thoại < **10%** thời lượng | `MIN_SPEECH_RATIO = 0.10` |
| ASR | Groq API, **whisper-large-v3-turbo**; bỏ qua nếu bài đã có transcript gốc | `app/providers/groq_asr.py`, `config.groq_asr_model` |
| Dịch | **2 lời gọi Gemini / đoạn** (dịch sát nghĩa → biên tập theo `budget_sec`) — gọi là "dịch hai pha" (KHÔNG phải "3 bước" như khóa luận) | `app/services/translation.py` `translate_batch` |
| LLM | Theo `.env` local: **`gemini-3.5-flash`** (code mặc định `gemini-2.5-flash` nếu env không đặt). Ghi vào bài đúng model đã dùng khi đo — `run_meta.json` có lưu. Hỏi Sang model trên server. | `config.gemini_model`, `.env` `GEMINI_MODEL` |
| TTS | **Azure Speech REST + SSML** `<prosody rate>` (KHÔNG phải Edge-TTS) | `app/providers/azure_tts.py` |
| Tỷ số tốc độ | **R = T_tts / T_orig** (code đảo chiều so với tài liệu "T_orig/T_exp" để có nghĩa) | `_speech_rate` |
| Nhánh | R ≤ 1.0 → đệm lặng; 1.0 < R ≤ 1.3 → tăng tốc `(R−1)·100%`; R > 1.3 → LLM rút gọn, tối đa **M = 2** lần, vẫn > 1.3 thì dùng **+30%** và log cảnh báo | `_synthesize_with_adaptive_rate`, `max_resummarize_attempts=2`, `MAX_TTS_RATE="+30%"` |
| Ghép | Chèn khoảng lặng gốc trước mỗi câu, đệm cuối đoạn → mỗi đoạn đúng thời lượng | `audio_utils.concat_with_leading_silence`, `pad_silence` |
| Chống trùng | Redis `SETNX` theo (lessonId, targetLanguage) | `be/.../dubbing/service/DubbingLockService.java` |
| Tái sử dụng | 1 bản lồng tiếng / (bài, ngôn ngữ) dùng chung; transcript gốc dùng lại cho ngôn ngữ khác | `dubbing_service.py` (`reuse_source`), BE `DubbingRequestService` |
| Hạn ngạch | 15 job/ngày (học viên), 30 (giảng viên) | BE `DubbingQuotaService` |
| Player | Dual Player: video tắt tiếng + audio riêng, đồng bộ chu kỳ **250 ms**, hỗ trợ YouTube IFrame API | FE |
| Kiến trúc | Spring Boot (nghiệp vụ) + Python FastAPI/Celery (AI) qua Redis; tiến độ Redis Pub/Sub → WebSocket; lưu trữ S3-compatible (Backblaze B2) | |
| DB | MySQL: `ai_jobs` (started_at, finished_at, total_chunks…), `audio_tracks`, `audio_chunks` (created_at), `transcripts` (is_source), `transcript_segments` (speech_rate, was_summarized) | `be/.../dubbing/entity/*` |

## 6. Việc cần làm (trạng thái ngày 09/11/2026)

### Đã xong
- [x] Khung bài báo đầy đủ 6 mục: Giới thiệu, Nghiên cứu liên quan, Phương pháp (hình pipeline TikZ, công thức R,
      chính sách 3 nhánh, Thuật toán 1), Triển khai, Thực nghiệm (khung), Kết luận; 11 tài liệu tham khảo thật.
- [x] Biên dịch sạch (không lỗi, không overfull).
- [x] Script đo: `run_experiment.py`, `analyze.py`, `server_job_stats.py/.sql` (đã viết, **chưa chạy**).

### Còn lại (theo thứ tự ưu tiên) — trước bước 2, 3 hỏi các thông tin ở mục 7
1. **Chọn 3–5 video** bài giảng tiếng Anh công khai (CNTT + kỹ năng mềm, 5–20 phút) → tạo
   `experiments/videos.json` theo mẫu `videos.example.json`.
2. **Chạy đo local** (khi hệ thống đã tối ưu xong — hỏi Sang trước):
   ```bash
   cd project/ai-worker            # để nạp đúng .env (GROQ/GEMINI/AZURE key)
   python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --max-chunks 1   # chạy thử rẻ
   python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --keep-audio     # chạy thật
   python NCKH/experiments/analyze.py NCKH/experiments/results/<run_id>
   ```
   ASR được cache trong `experiments/.cache/` → chạy lại không tốn Groq.
3. **Lấy số liệu server** (chỉ đọc; thời gian xử lý thật, thời gian ra đoạn đầu, phân bố speech_rate/was_summarized):
   mở SSH tunnel, đặt biến `NCKH_DB_HOST/PORT/USER/PASSWORD/NAME`, `pip install pymysql`, chạy
   `python NCKH/experiments/server_job_stats.py`. Sau đó `analyze.py <run_dir> --server <server_dir>`.
4. **Điền số liệu vào `paper/main.tex`** — ⚠️ *Cập nhật 10/11: người đo KHÔNG tự sửa `main.tex`; Sang và Thiện
   kiểm tra REPORT (mục 9.6) rồi mới điền.* Nội dung dưới đây chỉ để tham khảo:
   - Mục *Thiết lập thực nghiệm*: số video N, tổng phút X, cấu hình máy (local) và server.
   - Bảng `tab:results`: dán các dòng LaTeX mà `analyze.py` in ra.
   - Có thể thêm hình `figures/r_hist.pdf` (phân bố R một pha vs hai pha) — nhớ thêm vào zip Overleaf.
   - Viết mục *Kết quả* và *Thảo luận*; sửa câu kết quả trong **Tóm tắt** (vẫn giữ 150–250 từ).
5. (Tùy chọn) **Đánh giá cảm nhận (MOS)**: 5–10 người nghe các file `--keep-audio` của V2 và V4, chấm 1–5 cho
   độ tự nhiên và độ khớp hình.
6. Bổ sung email 3 tác giả, ngày nộp trong `\thanks{}`; kiểm tra dòng `\markboth` (Volume/số của SSRC-II'2026).
7. Rà lại toàn bài, xóa hết `\todo`, biên dịch, nộp trên hệ thống SSRC trước **15/11/2026**.

## 7. Thông tin cần hỏi trước khi đo (AI: hỏi người dùng, KHÔNG tự đoán)

Trước khi chạy bước 2–3 ở mục 6, hỏi người dùng các thông tin sau. **Không yêu cầu người dùng dán mật khẩu,
API key hay private key vào chat** — hướng dẫn họ tự đặt vào biến môi trường hoặc file `.env` (không commit).

**A. Đo local (`run_experiment.py`)**
1. Hệ thống đã tối ưu xong, được phép chạy đo chưa? (Sang đang tối ưu — phải có xác nhận.)
2. File `project/ai-worker/.env` đã có `GROQ_API_KEY`, Gemini key, Azure Speech key/region chưa? (Chỉ hỏi "đã có
   chưa", không hỏi giá trị.) Python env nào dùng để chạy `ai-worker` (venv / Docker container)?
3. Danh sách 3–5 video (link YouTube hoặc file .mp4), nhóm CNTT/Kỹ năng mềm, giọng đọc tiếng Việt muốn dùng.
4. Ngân sách API: được chạy đầy đủ hay chỉ `--max-chunks 1`? Có giữ audio (`--keep-audio`) để đánh giá MOS không?
5. Cấu hình máy chạy (CPU, RAM, tốc độ mạng) — để ghi vào mục Thiết lập thực nghiệm.

**B. Đọc số liệu server (`server_job_stats.py`)** — chủ server là bạn trong nhóm, chỉ được ĐỌC:
1. Địa chỉ server (IP/domain) và **user SSH**; đăng nhập bằng SSH key hay mật khẩu (người dùng tự nhập khi `ssh` hỏi).
2. MySQL chạy **trong Docker** (tên container? có publish cổng 3306 ra host không?) hay cài thẳng trên máy?
3. Tên database, **user MySQL** (tốt nhất là user chỉ có quyền SELECT); mật khẩu người dùng tự đặt vào
   biến môi trường `NCKH_DB_PASSWORD`.
4. Phiên bản code đang chạy trên server (nhánh/commit) — để ghi vào bài và để chắc schema khớp với
   `server_job_stats.sql` (bảng `ai_jobs`, `audio_tracks`, `audio_chunks`, `transcripts`, `transcript_segments`).
5. Khoảng thời gian/job nào nên loại bỏ (job test lỗi, job trước khi đổi sang Azure TTS…).

Cách kết nối gợi ý (sau khi có thông tin):
```bash
# Cửa sổ 1: mở tunnel (MySQL trên host)
ssh -N -L 3307:127.0.0.1:3306 <user>@<server>
# MySQL trong Docker không publish cổng: lấy IP container trên server
#   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <mysql_container>
#   rồi: ssh -N -L 3307:<ip_container>:3306 <user>@<server>

# Cửa sổ 2 (PowerShell): biến môi trường chỉ tồn tại trong phiên này
$env:NCKH_DB_HOST="127.0.0.1"; $env:NCKH_DB_PORT="3307"
$env:NCKH_DB_USER="<user>"; $env:NCKH_DB_NAME="<db>"
$env:NCKH_DB_PASSWORD = Read-Host "MySQL password"   # người dùng tự gõ
pip install pymysql
python NCKH/experiments/server_job_stats.py
```
Phương án thay thế nếu không mở tunnel được: copy `server_job_stats.sql` lên server, chạy
`docker exec -i <mysql_container> mysql -u <user> -p <db> < server_job_stats.sql > out.tsv` và gửi file kết quả về.

## 8. Giải thích script đo (để AI không phải đọc lại code)

- `run_experiment.py` import trực tiếp hàm của pipeline, **không sửa code app**, **không ghi DB**.
  - ASR 1 lần/video (cache) → với mỗi đoạn gọi Gemini 2 lần, lấy kết quả **pha 1 cho V1**, **pha 2 cho V2–V4**.
  - V1/V2: TTS tốc độ mặc định (câu ngắn được đệm lặng, câu dài bị tràn).
  - V3: chỉ tăng tốc tới +30%, không rút gọn.
  - V4: gọi đúng `dubbing_service._synthesize_with_adaptive_rate` (phương án đề xuất).
  - Đếm số lời gọi LLM/TTS bằng cách bọc hàm ở mức module.
  - `segments.csv`: `t_orig, t_tts_default, r_default, branch, applied_rate, n_resummarize, t_final, overrun, abs_delta, llm_calls, tts_calls`.
  - `videos.csv`: thời gian từng giai đoạn (giây), số lời gọi.
- `analyze.py`: Δ trung bình/trung vị/p95, % câu còn tràn, % R>1.3, số lời gọi LLM theo phương án; phân bố
  nhánh; thời gian/phút video; xuất `summary.md`, `summary.json`, dòng LaTeX cho Bảng `tab:results`.
- Khi script lỗi do code app đã đổi (tên hàm/tham số), sửa **script**, không sửa app trừ khi được yêu cầu.

---

## 9. Kế hoạch đo đợt 2 (cập nhật 10/11/2026) — ĐỌC TỪ ĐÂY

### 9.1. Tình trạng sau đợt 1 (run `20261109_042122`)

- 4 bài giảng (`lec01`–`lec04`, file `.mp3`), **603 câu**, chạy đủ 4 phương án V1–V4 với `--max-chunks 1`
  → mỗi bài **chỉ xử lý 10 phút đầu**, tổng **39,4 phút** (không phải 50 phút).
- Số liệu chất lượng đã được kiểm tra lại từ `segments.csv` và **khớp**:

  | Phương án | Δ TB (s) | % câu còn tràn | % R>1,3 sau | LLM |
  |---|---|---|---|---|
  | V1 một pha | 1,68 | 94,2 | 75,3 | 4 |
  | V2 hai pha | 0,99 | 82,9 | 48,3 | 8 |
  | V3 hai pha + tăng tốc | 0,32 | 48,1 | 18,6 | 8 |
  | V4 đề xuất | 0,16 | 23,5 | 13,8 | 444 |

- Đã sửa `analyze.py` (10/11): thời gian/phút giờ chia cho **thời lượng thực sự xử lý**
  (`min(duration, n_chunks × 600 s)`); trước đó chia cho cả độ dài file nên ra số nhỏ hơn thực tế.
  **Luôn chạy lại `analyze.py` sau khi pull** để `summary.md` đúng.
- Còn thiếu để bài báo đạt yêu cầu:
  1. Chưa có **nguồn gốc dữ liệu** (bài giảng lấy ở đâu, tác giả, giấy phép).
  2. Chưa chạy **toàn bộ độ dài** bài (chưa kiểm chứng ghép nhiều đoạn 10 phút).
  3. Chỉ chạy **1 lần** — LLM không tất định, chưa biết độ dao động.
  4. Chưa đánh giá **độ trung thành nội dung** của câu bị rút gọn (trung bình bị cắt 34% ký tự — có mất ý không?).
  5. Chưa có **đánh giá cảm nhận** của người nghe.
  6. Chưa có **thời gian xử lý thật trên server** và số liệu vận hành (tỷ lệ job thành công, tái sử dụng).

### 9.2. Nguyên tắc để số liệu hợp lệ cho bài NCKH

1. **Cố định cấu hình** trong cả đợt đo: không đổi code `app/`, `.env`, giọng đọc giữa các lần chạy. Ghi lại
   commit đang dùng (`git rev-parse --short HEAD`) vào `experiments/results/<run_id>/NOTES.md`.
2. **Không chọn lọc kết quả**: báo cáo mọi lần chạy, kể cả lần lỗi; video lỗi ghi lý do, không âm thầm bỏ.
3. **Đánh giá mù** khi cho người nghe chấm: không cho biết clip thuộc phương án nào, thứ tự ngẫu nhiên.
4. **Tách bạch môi trường**: chỉ số chất lượng (Δ, R, số lời gọi) đo **local**; thời gian triển khai đo
   **server**. Trong bài ghi rõ số nào đo ở đâu.
5. **Server chỉ ĐỌC**. Không tạo job, không sửa DB, không restart — trừ mục S4 khi Sang cho phép bằng lời.
6. Dữ liệu cá nhân (email, tên học viên trên server) **không** đưa vào CSV/commit — câu SQL chỉ lấy cột cần thiết.

### 9.3. Đo ở LOCAL

> Chạy trong môi trường có `ffmpeg`. Đợt 1 dùng đường dẫn `/app/NCKH/...` → đã chạy **trong container
> ai-worker**; giữ nguyên cách đó. Đứng ở thư mục gốc của ai-worker (`/app` trong container).

**L1 – Ghi nguồn dữ liệu** (bắt buộc, làm trước)
- Bổ sung `note` cho mỗi bài trong `experiments/videos.json`: *tên bài – người giảng/kênh – URL gốc – giấy phép
  (CC BY, MIT OCW, YouTube Standard…) – thời lượng*. Ưu tiên bài có giấy phép mở để trích dẫn được.
- Nếu thêm/thay bài: 4–6 bài, 10–20 phút, tiếng Anh, giọng rõ, chia đều 2 nhóm CNTT / Kỹ năng mềm,
  **ít nhất 2 bài dài hơn 10 phút** để có nhiều đoạn.

**L2 – Chạy đầy đủ độ dài (không giới hạn đoạn)**
```bash
python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r1 --keep-audio
python NCKH/experiments/analyze.py NCKH/experiments/results/full_r1
```
- ASR cache cũ chỉ có đoạn đầu → script tự gọi lại Groq cho cả bài (đúng, không phải lỗi).
- Kiểm tra thêm: ghép audio V4 của cả bài (các file `*_v4.mp3` + khoảng lặng theo `start/end` trong
  `.cache/<id>/asr_cache.json`) rồi đo tổng thời lượng ≈ thời lượng gốc (lệch < 1 s). Đây là bằng chứng
  cho mục "Ghép âm thanh" trong bài. Có thể viết script nhỏ `check_full_length.py` dùng `audio_utils`.

**L3 – Lặp lại để đo độ dao động**
```bash
python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r2 --variants V2,V4
python NCKH/experiments/run_experiment.py --manifest NCKH/experiments/videos.json --run-id full_r3 --variants V2,V4
```
- ASR dùng cache (không tốn Groq), chỉ dịch + TTS chạy lại. Báo cáo **trung bình ± độ lệch chuẩn** của Δ TB,
  % câu còn tràn, % câu rút gọn qua 3 lần. Có thể viết `aggregate_runs.py` gộp các `summary.json`.
- Nếu hết ngân sách API: tối thiểu 2 lần cho V4.

**L4 – Độ trung thành nội dung của câu bị rút gọn** (quan trọng — phản biện sẽ hỏi)
- Lấy ngẫu nhiên **50 câu** có `was_summarized = True` ở V4 của `full_r1` (seed cố định, ví dụ 42), xuất CSV:
  `src_text` (tiếng Anh), bản dịch V2 (trước rút gọn), bản dịch V4 (sau rút gọn).
- 2 người (Sang, Thiện) chấm **độc lập**: `2` = giữ đủ ý, `1` = mất ý phụ, `0` = mất/sai ý chính.
  Báo cáo % mỗi mức và độ đồng thuận giữa 2 người (tỷ lệ trùng, hoặc hệ số kappa của Cohen).
- Có thể cho LLM chấm thêm để tham khảo, nhưng **số chính trong bài là do người chấm**.
- Lưu: `results/full_r1/fidelity_sample.csv`, `results/full_r1/fidelity_scores.csv`.

**L5 – Đánh giá cảm nhận (MOS)** (nên có; không kịp thì ghi là hạn chế)
- Từ audio của `full_r1`, chọn **20 câu** phân tầng theo nhánh của V4 (pad / speedup / summarize / capped,
  mỗi nhánh 5 câu). Mỗi câu 2 clip: V2 và V4 → 40 clip, đặt tên ngẫu nhiên.
- Nếu có video gốc: cắt đúng đoạn `start–end` và ghép audio để người nghe chấm cả độ khớp hình:
  `ffmpeg -ss <start> -to <end> -i video.mp4 -i clip.mp3 -map 0:v -map 1:a -shortest out.mp4`.
  Nếu chỉ có mp3 thì chỉ chấm độ tự nhiên và độ dễ hiểu — ghi rõ trong bài.
- 8–15 người nghe, Google Form, mỗi clip thang 1–5: **độ tự nhiên**, **độ dễ hiểu**, (**độ khớp hình**).
  Thứ tự xáo trộn, không ghi tên phương án.
- Báo cáo MOS trung bình ± khoảng tin cậy 95% cho V2 và V4; kiểm định Wilcoxon theo cặp nếu đủ người.
- Lưu: `results/mos/clips_key.csv` (bảng giải mã — KHÔNG gửi người nghe), `results/mos/mos_responses.csv`.

**L6 – Cấu hình máy**: CPU, RAM, hệ điều hành, có chạy trong Docker không, tốc độ mạng → ghi vào `NOTES.md`.

### 9.4. Đo trên SERVER (chỉ đọc)

> Trước khi làm: hỏi Sang các thông tin ở **mục 7.B** (host, user SSH, MySQL trong Docker hay không, user DB).
> Không yêu cầu dán mật khẩu vào chat.

**S1 – Số liệu job thật**
```bash
python NCKH/experiments/server_job_stats.py
python NCKH/experiments/analyze.py NCKH/experiments/results/full_r1 --server NCKH/experiments/results/server_<ngày>
```
Từ `jobs.csv` báo cáo:
- Số job, tỷ lệ `COMPLETED` / `FAILED` / `SKIPPED`, số lần retry trung bình.
- **Thời gian xử lý / phút video** = `processing_sec / (lesson_duration_sec / 60)`: trung bình, trung vị, min–max.
- **Thời gian ra đoạn đầu tiên** (`first_chunk_sec`) — chứng minh lợi ích của chia đoạn 10 phút: người học
  nghe được sau X giây thay vì chờ cả bài.
- **Thời gian chờ hàng đợi** (`queue_wait_sec`).
- Loại job test/lỗi theo khoảng thời gian Sang chỉ định; ghi rõ số job bị loại và lý do.

**S2 – Tốc độ đọc trong vận hành thật** (`segments.csv` của server)
- Phân bố `speech_rate` (= 1.0, 1.0–1.3, = 1.3) và tỷ lệ `was_summarized`, so sánh với V4 ở local.
  Nếu tương đồng → kết quả local có tính đại diện (1–2 câu trong phần Thảo luận).

**S3 – Hiệu quả tái sử dụng** (`reuse.csv`)
- Số bản lồng tiếng (bài, ngôn ngữ) đã tạo và tổng `play_count` → trung bình mỗi bản được phát lại bao
  nhiêu lần, tức là số lần **không** phải chạy lại pipeline.
- Số bài có từ 2 ngôn ngữ trở lên → số lần bỏ qua ASR nhờ dùng lại transcript.

**S4 – (Tùy chọn, CẦN Sang cho phép bằng lời)** chạy 1–2 job mới trên server với bài trong tập thử nghiệm để
có thời gian thật của đúng dữ liệu đó. Không được phép thì bỏ qua, dùng S1.

**S5 – Xác nhận cấu hình server**: model Gemini, `CHUNK_MINUTES`, commit đang chạy. Chỉ đọc đúng biến cần
thiết, ví dụ `docker exec <ai-worker> printenv GEMINI_MODEL CHUNK_MINUTES` — **không in toàn bộ env** (có key).
Ghi vào `NOTES.md` và REPORT. **Không sửa `main.tex`.**

### 9.5. Kết quả cần nộp lại

```
experiments/results/
├── full_r1/  full_r2/  full_r3/   segments.csv, videos.csv, run_meta.json, summary.md/json, NOTES.md
│                                  (KHÔNG commit thư mục audio/ — đã có trong .gitignore)
├── full_r1/fidelity_sample.csv, fidelity_scores.csv
├── mos/clips_key.csv, mos_responses.csv        (nếu làm L5)
└── server_<ngày>/jobs.csv, segments.csv, reuse.csv, NOTES.md
```
- `NOTES.md` mỗi thư mục: commit, cấu hình máy/server, người chạy, ngày giờ, sự cố gặp phải.
- Commit + push lên nhánh **`NCKH`** kèm file REPORT (mục 9.6), nhắn Sang.
- **KHÔNG sửa `paper/main.tex`** và không sửa file kết quả cũ của người khác. Sang và Thiện sẽ đọc REPORT,
  kiểm tra lại số liệu, rồi tự điền vào bài.

### 9.6. REPORT đo đạc (đầu ra bắt buộc)

Mỗi đợt đo phải có **một file report** để người khác đọc là hiểu đã làm gì, làm như thế nào và ra kết quả gì,
đủ để **tự kiểm tra lại hoặc chạy lại** được.

- Vị trí: `NCKH/experiments/reports/REPORT_<yyyymmdd>_<tên người đo>.md` (ví dụ `REPORT_20261112_Thien.md`).
- AI viết report từ **dữ liệu thật** trong các file kết quả; mọi con số phải truy được về file CSV/JSON nguồn.
  Không làm tròn khác đi, không tự diễn giải thành "tốt/xấu" trong phần số liệu.
- Một lần chạy lỗi hay một bước bị bỏ qua cũng phải ghi vào, kèm lý do.

**Mẫu report** (giữ nguyên các mục, mục nào không làm thì ghi "Không thực hiện – lý do"):

````markdown
# REPORT đo đạc – <ngày> – <người đo>

## 0. Tóm tắt nhanh
- Đã làm: L1, L2, ... / S1, ...   Chưa làm: ... (lý do)
- 3–5 con số chính (kèm file nguồn).
- Vấn đề cần nhóm xem lại: ...

## 1. Môi trường
| Mục | Local | Server |
|---|---|---|
| Commit ai-worker (`git rev-parse --short HEAD`) | | |
| Chạy ở đâu (container / máy) | | |
| CPU / RAM / OS | | |
| Mạng (tải lên/xuống) | | – |
| GEMINI_MODEL / ASR model / giọng đọc | | |
| CHUNK_MINUTES, MAX_RESUMMARIZE_ATTEMPTS | | |
| Thời gian bắt đầu – kết thúc | | |

## 2. Dữ liệu
| id | Tên bài | Nguồn (URL) | Giấy phép | Nhóm | Thời lượng | Số câu |
|---|---|---|---|---|---|---|
Cách lấy dữ liệu: tải từ đâu, chuyển định dạng thế nào (lệnh ffmpeg/yt-dlp đã dùng).

## 3. Các bước đã thực hiện
Với MỖI mục (L1…L6, S1…S5):
- **Mục đích**: đo cái gì.
- **Lệnh đã chạy** (copy nguyên văn, kể cả tham số `--run-id`, `--variants`, `--max-chunks`).
- **Thay đổi so với hướng dẫn** (nếu có) và lý do.
- **File đầu ra**: đường dẫn.
- **Sự cố**: lỗi gặp phải, cách xử lý, có chạy lại không.
Script tự viết thêm (ví dụ `check_full_length.py`, `aggregate_runs.py`, chọn mẫu L4/L5): ghi tên file,
chức năng, seed ngẫu nhiên, và commit file đó cùng report.

## 4. Kết quả
### 4.1. So sánh V1–V4 (từ `summary.json` của từng run)
| Phương án | run | n câu | Δ TB | Δ trung vị | Δ p95 | % còn tràn | % R>1,3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|---|
Nếu có nhiều run: thêm dòng trung bình ± độ lệch chuẩn, ghi rõ cách tính.

### 4.2. Phân bố nhánh của V4 và phân bố R
### 4.3. Kiểm tra toàn bộ độ dài (L2): thời lượng gốc / thời lượng audio ghép / chênh lệch, theo từng bài
### 4.4. Độ trung thành câu rút gọn (L4): số câu, % mức 2/1/0 từng người chấm, độ đồng thuận, 3–5 ví dụ
### 4.5. MOS (L5): số người nghe, số clip, trung bình ± KTC 95% cho V2/V4, kiểm định (nếu có)
### 4.6. Server (S1–S3): số job (tổng / bị loại và lý do), tỷ lệ trạng thái, thời gian xử lý/phút,
thời gian ra đoạn đầu, thời gian chờ hàng đợi, phân bố speech_rate, tỷ lệ was_summarized, play_count
### 4.7. Cấu hình server xác nhận được (S5)

## 5. Điểm bất thường và nghi vấn
- Số liệu lạ (ví dụ R rất lớn ở câu rất ngắn, câu dịch rỗng, video có Δ khác hẳn các video khác).
- Chỗ không chắc là đo đúng hoặc tính đúng.
- Khác biệt giữa local và server.

## 6. Cách kiểm tra lại
Lệnh tối thiểu để người khác tái tạo con số trong mục 4 (ví dụ chạy lại `analyze.py` trên thư mục kết quả).

## 7. Danh sách file đã commit
````

**Tự kiểm tra trước khi nộp**:
- [ ] Mọi con số trong mục 4 đều có file nguồn đi kèm trong `results/`.
- [ ] Đã chạy lại `analyze.py` (bản đã sửa ngày 10/11) trên mọi thư mục run.
- [ ] Không có mật khẩu, key, email hay tên học viên trong report/CSV.
- [ ] Không có thư mục `audio/` hoặc `.cache/` trong commit.
- [ ] Không sửa `paper/main.tex`.

### 9.7. Thứ tự ưu tiên (hạn nộp 15/11)

1. **Bắt buộc**: L1 → L2 → S1 → S5 → L6
2. **Rất nên**: L4 → L3 → S2 → S3
3. **Nếu kịp**: L5 (MOS), S4

Chỉ kịp nhóm 1 thì bài vẫn nộp được; các mục còn lại ghi vào phần *Hạn chế và hướng phát triển*.
