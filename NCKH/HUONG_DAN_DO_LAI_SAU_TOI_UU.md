# Hướng dẫn đo lại sau đợt tối ưu dubbing (đợt 3, viết ngày 22/11/2026)

> **Dành cho AI (Claude) của thành viên đo.** Đưa nguyên file này cho Claude và nói:
> *"Đọc NCKH/HUONG_DAN_DO_LAI_SAU_TOI_UU.md rồi làm theo, hỏi tôi trước mỗi bước có đánh dấu ❓."*
> Trả lời bằng **tiếng Việt**.
>
> **Bắt buộc đọc trước:** `NCKH/CAP_NHAT_SAU_TOI_UU_DUBBING.md` **mục 6** (kinh nghiệm đo đạc: đọc log TIMING,
> xóa dữ liệu cũ, bẫy môi trường, bẫy khi đo độ khớp, số liệu tham khảo job 43–46 để tự kiểm tra số đo có hợp lý không).
>
> Nên đọc kèm (chỉ để tra cứu, không cần đọc hết): `NCKH/CAP_NHAT_SAU_TOI_UU_DUBBING.md` mục 1–5 (pipeline đã đổi gì),
> `docs/improve/performance/SoSanh_GhepChunk.md` mục 6 (checklist build server), `NCKH/HUONG_DAN_NHOM.md` mục 3 và 9.2 (quy tắc chung).

## 0. Bối cảnh trong 5 dòng

- Bài báo SSRC-II'2026 đã nộp ngày 14/11 với số liệu đo trên **bản cũ** (commit `e5a8cb7`, Gemini 3.5 Flash, dịch hai pha, tăng tốc bằng SSML, rút gọn từng câu).
- Sau đó pipeline đã được tối ưu nhiều đợt. `paper/main.tex` **đã được viết lại phần Phương pháp** theo bản mới, nhưng **toàn bộ số liệu (Bảng 2–4, L4, Tóm tắt, Kết luận) vẫn là số cũ**, đánh dấu chữ đỏ `\todo{...}`.
- Hạn nộp **bản chính thức: 04/12/2026**. Cần đo lại trên bản mới và nộp REPORT để Sang kiểm tra rồi mới điền vào bài.
- Bản mới khác bản cũ ở: **một lời gọi dịch có `max_chars`**, **tăng tốc bằng FFmpeg `atempo`** (không gọi lại TTS), **rút gọn theo lô**, **mốc đầu câu theo từ đầu tiên**, **Gemini 3.6 Flash, thinking `minimal`**, **giữ nhạc nền bật**, **dây chuyền 2 công đoạn** cho bài nhiều chunk.
- Độ dài đoạn vẫn là **L = 600 s**; xếp câu theo mốc tuyệt đối, tăng tốc cả đoạn tối đa ×1,15 **không đổi**.

## 1. Quy tắc bắt buộc

1. **Không sửa `paper/main.tex`**, không sửa code trong `app/` (trừ khi Sang đồng ý). Chỉ sửa và thêm file trong `NCKH/experiments/`.
2. **Cố định cấu hình suốt đợt đo**: cùng một commit, cùng `.env`, cùng giọng đọc. Ghi tất cả vào `NOTES.md`.
3. **Không trộn số cũ và số mới** trong cùng một bảng hay một phương án. Số cũ chỉ để tham chiếu và phải ghi rõ "bản `e5a8cb7`".
4. **Server**: được build lại 3 container ai (`ai-api`, `ai-worker`, `ai-beat`) và chạy script đo trong `lms_ai_worker`. **Không đụng** DB schema, volume, `backend`, `frontend`. Chỉ đọc DB bằng SELECT, **trừ một ngoại lệ đã được Sang cho phép (22/11)**: xóa dữ liệu lồng tiếng cũ của **đúng 4 bài thử nghiệm** (lesson 2284, 2285, 2286, 2288 trong khóa 92) bằng `NCKH/experiments/reset_lessons.sql` và `reset_lessons_cache.py` (mục 3, bước A6). Không xóa gì khác.
5. **Bí mật**: không in, không commit `.env`, token Modal, key Gemini/Azure/Groq. Kiểm tra env bằng `printenv TÊN_BIẾN` cụ thể, **không** `printenv` toàn bộ.
6. Không chọn lọc kết quả; lần chạy lỗi cũng ghi vào report kèm lý do.
7. Commit và push lên nhánh **`NCKH`** khi xong, rồi nhắn Sang.

## 2. Phân công: AI tự làm gì, hỏi Thiện gì

**AI tự làm (không cần hỏi):** merge code về server (bước A1), build lại container, kiểm tra cấu hình, xóa dữ liệu cũ
của 4 bài (đã được Sang cho phép), chạy script đo, **theo dõi và kiểm tra các job lồng tiếng thật** qua log và DB
(bước C4), viết REPORT, commit và push.

**❓ Hỏi Thiện** (người đang ngồi ở server; không yêu cầu dán mật khẩu hay key vào chat):
- ❓ Thư mục trên server: repo ai-worker ở đâu (thường `/var/lms/ai-worker`), file `docker-compose.yml` ở đâu (thường `/var/lms/be`), nhánh đang deploy là nhánh nào?
- ❓ **`.env`**: đã có `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` đúng tài khoản deploy hàm `lms-demucs` bản mới (commit `34052fb`) chưa? Key Gemini còn hạn không? (Chỉ hỏi "đã có chưa"; nếu cần sửa `.env`, AI chỉ ra dòng cần sửa để Thiện tự mở file sửa.)
- ❓ **Credit Gemini** còn bao nhiêu? Đợt đo ước khoảng 20–40K₫. Dưới khoảng 50K₫ thì nhắc Thiện nạp trước.
- ❓ User và tên database MySQL (mật khẩu Thiện tự nhập khi lệnh hỏi).
- ❓ Có job lồng tiếng thật nào đang chạy không (để không build/tạo lại container giữa chừng)?
- ❓ Ở bước C4: nhờ Thiện **bấm "Lồng tiếng" tiếng Việt trên web** cho từng bài khi AI báo sẵn sàng (AI không tự thao tác giao diện web); phần theo dõi và kiểm tra job thì AI tự làm.

## 3. Bước A — Build lại môi trường trên server

> Server có thể còn image, container và `.env` của đợt trước (3.5 Flash, không có `modal`, FFmpeg 5.1).
> **Phải build lại**, không chỉ `restart`.

```bash
# A0. Ghi lại trạng thái cũ (dán vào NOTES)
docker exec lms_ai_worker sh -c "ffmpeg -version | head -1; cat /etc/debian_version"
docker exec lms_ai_worker printenv GEMINI_MODEL DUBBING_THINKING_LEVEL BGM_SEPARATION
cd /var/lms/ai-worker && git log --oneline -1

# A1. Merge code mới về server (AI tự làm). Code chạy là code của nhánh đang checkout trong thư mục
#     được gắn vào container (mục 6.4.2), nên phải đúng nhánh và đủ code mới.
cd /var/lms/ai-worker
git status --short                                     # có thay đổi chưa commit? -> dừng, ❓ hỏi Thiện, KHÔNG xóa
git fetch origin
git checkout develop && git pull --ff-only origin develop   # nhánh deploy (theo câu trả lời của Thiện)
git merge --no-edit origin/NCKH                        # lấy script đo mới nhất (nếu đã có trong develop thì báo "Already up to date")
#   Conflict -> dừng, `git merge --abort`, ❓ báo Thiện/Sang, không tự giải quyết conflict trong app/.
git log --oneline -1                                   # ghi commit này vào NOTES
grep -c "place_on_timeline_ffmpeg" app/audio_utils.py   # phải > 0
grep -c "_prepare_chunk_with_retry" app/services/dubbing_service.py   # phải > 0 (bản có dây chuyền)
ls NCKH/experiments/run_experiment_v2.py NCKH/experiments/reset_lessons.sql   # phải có
grep -c "prefetch" app/services/dubbing_service.py      # phải > 0 (dây chuyền chunk)
```

**A2. Sửa `.env` của ai-worker trên server** (mở bằng trình soạn thảo, không `cat` ra màn hình):

| Biến | Giá trị |
|---|---|
| `GEMINI_MODEL` | `gemini-3.6-flash` |
| `GEMINI_MODELS` | **để trống** (không có model dự phòng, để mọi câu dùng cùng một model) |
| `DUBBING_THINKING_LEVEL` | `minimal` |
| `BGM_SEPARATION` | `modal` (giữ nhạc nền **bật**, theo quyết định của Sang) |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | token đúng tài khoản deploy `lms-demucs` |
| `TIMELINE_ENGINE` | `ffmpeg` (mặc định, có thể không đặt) |
| `CHUNK_MINUTES` | `10` |
| `MAX_RESUMMARIZE_ATTEMPTS` | `2` |
| `MIN_RESUMMARIZE_FRAME_SEC` | `2.0` (mặc định) |

```bash
# A3. Build lại từ base image mới, tạo lại container để nạp .env mới
cd /var/lms/be            # thư mục chứa docker-compose.yml
docker compose build --pull --no-cache ai-api ai-worker ai-beat
docker compose up -d --force-recreate --no-deps ai-api ai-worker ai-beat

# A4. Kiểm tra (dán kết quả vào NOTES)
docker exec lms_ai_worker sh -c "ffmpeg -version | head -1; cat /etc/debian_version"   # ffmpeg 7.x, Debian 13.x
docker exec lms_ai_worker printenv GEMINI_MODEL DUBBING_THINKING_LEVEL BGM_SEPARATION   # gemini-3.6-flash / minimal / modal
docker exec lms_ai_worker python -c "from app.config import settings as s; print(s.timeline_engine, s.bgm_separation, s.chunk_minutes, s.max_resummarize_attempts, s.min_resummarize_frame_sec, s.tts_concurrency)"
docker exec lms_ai_worker python -c "import modal; modal.Function.from_name('lms-demucs','separate').hydrate(); print('modal ok')"
docker inspect -f '{{.State.Status}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' lms_ai_worker
```

- Giữ cấu hình log (`max-size 10m`, `max-file 3`) và `--reload-exclude "NCKH/experiments/*"` đã thêm ngày 13/11 trong `docker-compose.yml`. Nếu bị mất sau khi pull, thêm lại và ghi vào NOTES.
- **Lưu ý:** `restart` **không** nạp lại `.env`; phải `up -d --force-recreate`.
- Nếu một bước kiểm tra sai: dừng lại, ghi lỗi vào report, ❓ hỏi Sang.

**A5. Gọi thử Gemini 1 lần** (bẫy key hết hạn/hết credit, mục 6.4.4) — nếu lỗi 401/402 thì dừng, ❓ báo Thiện:
```bash
docker exec -w /app lms_ai_worker python -c "import asyncio; from app.providers import gemini; print(asyncio.run(gemini.generate('Tra loi dung 1 tu: ok', thinking_level='minimal')).text)"
```

**A6. Xóa dữ liệu cũ của 4 bài thử nghiệm** (đã được Sang cho phép; mục 6.3 của file cập nhật).
Hệ thống dùng lại bản ký âm, bản dịch, bản lồng tiếng, nhạc đã tách và tốc độ đọc của giọng; bản ký âm cũ còn dùng
**mốc đầu câu kiểu cũ**, nên không xóa thì Bảng 3, Bảng 4 đều sai.
```bash
# (1) MySQL — xem trước, xóa trong 1 transaction, kiểm tra lại (Thiện tự nhập mật khẩu)
docker exec -i lms_mysql mysql -u <user> -p <db> < NCKH/experiments/reset_lessons.sql
# (2) B2 nhạc đã tách + Redis: chạy dry-run trước, đọc danh sách, rồi mới --apply
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/reset_lessons_cache.py \
    --lessons 2284,2285,2286,2288 --reset-cps --course-cache
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/reset_lessons_cache.py \
    --lessons 2284,2285,2286,2288 --reset-cps --course-cache --apply
```
- Ghi vào NOTES: số dòng trước khi xóa (phần SELECT đầu file SQL), số object B2 đã xóa, **giá trị `tts_cps` trước khi xóa**.
- Xóa `tts_cps` để lần V4 đầu (C1) đúng là "giọng chưa có số đo"; C2 là lần đã có số đo.
- Lệnh SQL chỉ chạm đúng 4 lesson trên. Nếu `SELECT` đầu file cho thấy lesson khác hoặc số dòng bất thường → dừng, ❓ hỏi Thiện.
- Embedding Gia sư AI trên Supabase của bài cũ vẫn còn (không ảnh hưởng số đo) — không cần xóa.

## 4. Bước B — Script đo (ĐÃ VIẾT SẴN, chỉ cần chạy thử)

Sang đã viết sẵn **`NCKH/experiments/run_experiment_v2.py`** cho pipeline mới (ngày 22/11/2026) và sửa kèm
`analyze.py` (đếm lời gọi LLM/TTS theo từng phương án, tên phương án mới) và `check_full_length.py` (ghép bằng
`place_on_timeline_ffmpeg` khi `TIMELINE_ENGINE=ffmpeg`, bỏ qua câu chỉ có dấu câu). Đã chạy thử bằng dữ liệu
giả lập (`_smoke_v2.py`, không gọi API) cho cả 4 phương án, gồm nhánh rút gọn theo lô.
**Không dùng `run_experiment.py` cũ** (lỗi trên code mới; chỉ giữ để tái lập số của `e5a8cb7`).

**Việc của AI người đo ở bước này:**
```bash
# B1. Kiểm tra code (không gọi API, khoảng 10 giây)
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/_smoke_v2.py | tail -5
# B2. Dọn cache ASR cũ (mốc đầu đoạn) để ASR chạy lại với mốc theo từ đầu tiên
docker exec --user 1000:1001 -w /app lms_ai_worker sh -c "mv NCKH/experiments/.cache NCKH/experiments/.cache_old_e5a8cb7 2>/dev/null; true"
# B3. Chạy thử thật, rẻ: 1 bài, 1 chunk
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/run_experiment_v2.py \
    --manifest NCKH/experiments/videos.json --run-id smoke_real --only lec01 --max-chunks 1 --keep-audio
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/analyze.py NCKH/experiments/results/smoke_real
```
Nếu B1 hoặc B3 lỗi: **dừng**, gửi nguyên log lỗi cho Sang, không tự sửa code trong `app/`. Được sửa script
trong `NCKH/experiments/` nếu lỗi rõ ràng do script; ghi lại thay đổi trong report.
Sau B3 xóa thư mục `results/smoke_real` (chỉ là chạy thử) **hoặc** giữ lại nhưng ghi rõ trong report là không dùng.

Tham khảo, cách script định nghĩa các phương án (khớp `main.tex`):

| PA | Dịch | Tăng tốc | Rút gọn | Cách gọi |
|---|---|---|---|---|
| **V1** | không ràng buộc độ dài: `translation._build_direct_prompt` + `gemini.generate` | không | không | TTS 1 lần, câu ngắn hơn khung coi `t_final = t_orig` |
| **V2** | `translation.translate_batch(segments, src, tgt, max_chars=None)` (chỉ ngân sách thời lượng) | không | không | như V1 |
| **V3** | `translate_batch` **có** `max_chars = max(4, int(cps × T_orig × 1,15))` (cps đọc từ Redis như pipeline; nếu chưa có thì ghi rõ và dùng `None`) | `audio_utils.change_tempo(path, min(R, 1,3))` | **không** | TTS 1 lần rồi atempo |
| **V4** | như V3 | như pipeline | như pipeline | gọi thẳng `dubbing_service._synthesize_segments(segments, texts, voice, out_paths, tgt)` cho **cả chunk** |

Script đã làm sẵn các điểm sau (để AI đối chiếu khi đọc kết quả, **không cần làm lại**):
- **V3 và V4 dùng chung một kết quả dịch** (cùng một lời gọi `translate_batch` có `max_chars`), giống cách đợt trước V2–V4 dùng chung bản dịch. Như vậy khác biệt giữa V3 và V4 chỉ còn là bước rút gọn.
- **Mốc câu** dùng đúng như pipeline: ASR qua `groq_asr.transcribe` (đã lấy mốc theo từ đầu tiên) rồi `dubbing_service.clamp_stt_segments`. **Không dùng lại `asr_cache.json` cũ** (mốc cũ là mốc đầu đoạn): xóa hoặc đổi tên thư mục `.cache/` trước khi chạy để ASR chạy lại.
- Câu chỉ có dấu câu: xử lý như pipeline (`dubbing_service._has_speakable_text`), ghi số câu bị bỏ.
- Đếm lời gọi bằng cách vá `gemini.generate` (đếm tất cả lời gọi LLM, kể cả dịch lại câu bị bỏ sót) và `azure_tts.synthesize`; đếm riêng số lời gọi `resummarize_batch` và **số câu** được rút gọn.
- Ghi `t_final` sau atempo: `max(độ dài file, t_orig)`, giống cách tính cũ. `applied_rate` = hệ số atempo.
- `run_meta.json` ghi thêm: `gemini_model`, `dubbing_thinking_level`, `bgm_separation`, `tts_concurrency`, giá trị `tts_cps` của từng giọng **trước** và **sau** khi chạy, commit.
- Chạy thử `--max-chunks 1 --only lec01` trước, kiểm tra không lỗi, rồi mới chạy đủ.
- `check_full_length.py` phải ghép bằng **đúng hàm của pipeline hiện tại** (`audio_utils.place_on_timeline_ffmpeg` nếu `TIMELINE_ENGINE=ffmpeg`), mốc `b_i` lấy từ ASR mới.

## 5. Bước C — Đo

> Tất cả chạy trong `lms_ai_worker` trên server, cùng commit ở A1, như đợt trước:
> `docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/...`

| # | Việc | Lệnh / cách làm | Số liệu cho bảng nào |
|---|---|---|---|
| C1 | **V1–V4** trên 4 bài (`videos.json`), toàn bộ độ dài, giữ audio | `run_experiment_v2.py --manifest NCKH/experiments/videos.json --run-id v3_r1 --keep-audio` rồi `analyze.py results/v3_r1` | Bảng 2 |
| C2 | **V4 lần 2** (đã có `tts_cps` sau C1) | `--variants V4 --run-id v3_r2` | Bảng 2: báo **cả 2 lần** V4; Sang chọn lần chính |
| C3 | **Độ trễ theo trục thời gian** | `check_full_length.py results/v3_r1 --variants V2,V4 --assembly new` và `drift_analysis.py` | Bảng 3 (dòng (c) mới) |
| C4 | **4 job thật qua web** (lần lồng tiếng đầu: dữ liệu cũ đã xóa ở A6, có ASR và tách nhạc). ❓ Nhờ Thiện bấm "Lồng tiếng" `vi-VN` **từng bài một**; AI tự theo dõi và kiểm tra (xem dưới). **Không chạy song song với C1–C2** | Log: `docker logs --timestamps --since <giờ bắt đầu> lms_ai_worker 2>&1 \| python3 -I NCKH/experiments/parse_worker_logs.py --out results/server_<ngày>/worker_logs.json`; DB: `server_job_stats.py` / `server_job_stats_ext.sql` | Bảng 4 |
| C5 | **L4**: chọn 50 câu rút gọn mới của V4 (`sample_fidelity.py results/v3_r1 --n 50 --seed 42 --min-frame 2.0 --baseline V3`; dùng **V3** làm bản dịch đầy đủ vì đó là đúng văn bản V4 nhận trước khi rút gọn), tạo file chấm có cột câu gốc EN, bản dịch đầy đủ trước rút gọn, bản rút gọn, **không có điểm** | Gửi file cho **Sang và Thiện chấm độc lập**, sau đó thống nhất câu lệch (như lần trước) | Đoạn L4 |

**C4 — AI tự theo dõi và kiểm tra từng job** (không cần Thiện làm gì ngoài bấm nút):
1. Trước khi Thiện bấm: ghi giờ UTC hiện tại (`date -u +%FT%TZ`) làm mốc `--since`.
2. Trong lúc chạy: `docker logs --timestamps -f --since <mốc> lms_ai_worker 2>&1 | grep -E "Bat dau pipeline|TIMING|BGM|HET CREDIT|401|Traceback|that bai"`
   (dừng theo dõi khi thấy `TIMING job=N final=`). Kiểm tra trạng thái bằng SQL chỉ đọc:
   `SELECT id, lesson_id, status, total_chunks, done_chunks, started_at, finished_at FROM ai_jobs WHERE lesson_id IN (2284,2285,2286,2288) ORDER BY id;`
3. Sau mỗi job, tự đối chiếu (mục 6.1, 6.4, 6.6 của file cập nhật):
   - `status = COMPLETED`, `done_chunks = total_chunks`, không có dòng lỗi.
   - Chunk 0 có `asr` **lớn hơn 0** (nếu `asr=0.0s` là đã dùng lại bản ký âm → A6 chưa xóa đúng, dừng và báo).
   - Có dòng `BGM tach nhac xong` (không phải `BGM dung lai nhac da tach tren B2` — nếu có là B2 chưa xóa).
   - `ghep` vài giây mỗi chunk, `tts` dưới khoảng 60 s mỗi chunk 10 phút; lệch xa số tham khảo job 43–46 → nghi sai phiên bản/cấu hình, dừng và báo.
   - `upload` > 30 s là bất thường (B2 treo): ghi chú; ❓ hỏi Thiện có chạy lại bài đó không (phải xóa lại dữ liệu bài đó bằng A6 trước khi chạy lại).
4. Chỉ khi job trước xong và kiểm tra ổn mới báo Thiện bấm bài tiếp theo.

Với C4, mỗi job ghi: thời lượng bài, số chunk, `processing_sec`, `first_chunk_sec`, thời gian giữa các chunk, trạng thái, số lần thử lại, và các dòng `TIMING` (asr, dịch, chờ chunk trước, tts, ghép, nhạc, tải lên). Bài > 10 phút (lec02, lec03, lec04) có nhiều chunk: kiểm tra dây chuyền chạy (có `cho_chunk_truoc` trong log).

## 6. Đầu ra — REPORT để Sang kiểm tra

Tạo `NCKH/experiments/reports/REPORT_<yyyymmdd>_<tên>.md` theo **mẫu ở `HUONG_DAN_NHOM.md` mục 9.6**, bổ sung:
- Mục **Môi trường**: kết quả các lệnh A0, A4, A5 (trước/sau build), commit, model, thinking, nhạc nền, `tts_cps`.
- Bảng V1–V4 của `v3_r1`, dòng V4 của `v3_r2`, và **một dòng tham chiếu "bản cũ e5a8cb7"** lấy từ `results/post_fix_r1/summary.json` (ghi rõ là số cũ).
- Bảng độ trễ theo trục thời gian (cũ và mới, ghi rõ nguồn).
- Bảng 4 job thật: số mới cạnh số cũ (`results/server_20261113`).
- Số câu L4 đã chọn và đường dẫn file chấm.
- Phần **Bất thường**: ví dụ R rất lớn, câu bị bỏ sót khi dịch, chunk rơi về tăng tốc tối đa do rút gọn lỗi, log `HET CREDIT (402)`, lần tách nhạc lỗi.
- Phần **Cách kiểm tra lại**: lệnh tái tạo từng con số.

Lưu kết quả ở `NCKH/experiments/results/v3_r1/`, `v3_r2/`, `server_<ngày>/`. **Không commit** `audio/`, `.cache/`, `media/`, video.

## 7. Checklist trước khi nhắn Sang

- [ ] `printenv` trong container ra `gemini-3.6-flash`, `minimal`, `modal`; ghi vào NOTES.
- [ ] Mọi lần chạy dùng cùng commit; commit có trong NOTES.
- [ ] ASR đã chạy lại (không dùng `asr_cache.json` cũ).
- [ ] Số trong REPORT truy được về file trong `results/`.
- [ ] Không sửa `paper/main.tex`, không commit bí mật.
- [ ] Đã push nhánh `NCKH`.
