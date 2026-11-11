# Báo cáo tình hình thực nghiệm và hướng hoàn thiện bài NCKH (11/11/2026)

> Người đọc: Sang (tác giả pipeline lồng tiếng và bài báo). Soạn bởi Thiện cùng Claude Code, dựa trên `paper/main.tex`,
> `HUONG_DAN_NHOM.md`, kết quả đợt 1 (`results/20261109_042122`) và đợt 2 (`results/full_r1`).
> **Chưa sửa bất kỳ code app nào và chưa sửa `paper/main.tex`.** Mọi đề xuất sửa pipeline bên dưới là để Sang quyết định.
> Báo cáo đo đạc chi tiết theo mẫu 9.6: `REPORT_20261110_Thien.md` (cùng thư mục).

## 0. Tóm tắt (đọc phần này là đủ nếu ít thời gian)

1. **Thuật toán chỉnh tốc độ đọc hoạt động đúng như thiết kế** ở mức từng câu: V4 giảm độ lệch Δ trung bình từ 1,65 s (V1) xuống 0,19 s,
   % câu còn tràn từ 94,0 xuống 26,7 (50 phút, 787 câu, `full_r1`).
2. **Phát hiện quan trọng: audio lồng tiếng sau khi ghép dài hơn video gốc và các câu trễ dần.** Đo trên audio ghép thật:
   V4 dài hơn bản gốc +1,7% đến +10,7% (+9,4 s đến +95,9 s), tệ nhất ở bài 15 phút (`lec04`). V2 dài hơn +18% đến +34%.
   Điều này **mâu thuẫn trực tiếp với câu trong bài báo** "âm thanh mỗi đoạn có thời lượng đúng bằng L … không tích lũy độ trễ giữa các đoạn" (mục 4).
   Với video ngắn (~10 phút) lệch chỉ vài giây nên khó thấy bằng tai; video càng dài càng lệch nhiều.
3. **Nguyên nhân nằm ở cách ghép audio**, không phải ở thuật toán chỉnh tốc độ (mục 4.2). Mô phỏng offline cho thấy xếp câu theo **mốc tuyệt đối**
   thay vì khoảng lặng tương đối giảm độ trễ tối đa của V4 từ 96 s xuống ~18 s ở `lec04`, và **không tốn API** (mục 4.4).
4. **Dữ liệu chưa đạt mô tả trong bài:** cả 4 bài đều là CNTT (không có kỹ năng mềm), chỉ có audio, giấy phép chưa xác minh, mới có 1 lần chạy đầy đủ (mục 6).
5. **Vận hành:** credit Gemini hết ngày 10/11 (≈ 109₫ mỗi lần gọi, ≈ 75K₫ cho một lượt V4 50 phút) nên chưa chạy được L3 và lồng tiếng thật qua web (mục 7).
6. **Cần Sang quyết định** (mục 9): sửa pipeline hay giữ nguyên và sửa bài báo; chạy thật trên web (S4); chốt phiên bản code để đo.

## 1. Bài báo đang khẳng định gì (liên quan tới số liệu)

| Trích từ `paper/main.tex` | Cần bằng chứng gì |
|---|---|
| Tóm tắt: "nhờ đó âm thanh lồng tiếng **luôn khớp với hình ảnh** mà vẫn giữ được độ tự nhiên" | Độ trễ mốc câu so với video; MOS về độ tự nhiên/khớp hình |
| Mục 3.6: "âm thanh của mỗi đoạn có thời lượng **đúng bằng L**, và tệp cuối cùng … có thời lượng bằng video gốc, **không tích lũy độ trễ giữa các đoạn**" | Thời lượng audio ghép so với video gốc (đã đo, **không khớp**) |
| Tóm tắt, mục 5.1: thực nghiệm trên video "công nghệ thông tin **và kỹ năng mềm**" | Dữ liệu cả hai nhóm (hiện chỉ có CNTT) |
| Mục 3.5: rút gọn "giữ ý chính" | Chấm độ trung thành của câu bị rút gọn (L4, chưa có người chấm) |
| Mục 1, 4.2: chia đoạn 10 phút cho phản hồi sớm; tái sử dụng giảm chi phí | Số liệu job thật trên server (S1–S3, chưa lấy) |

## 2. Đã làm gì

| Đợt | Phạm vi | Số liệu |
|---|---|---|
| Đợt 1 (`20261109_042122`) | 4 audio, **10 phút đầu mỗi bài** (`--max-chunks 1`), 39,4 phút, 603 câu, V1–V4, 1 lần | `results/20261109_042122/` |
| Đợt 2 (`full_r1`) | Cùng 4 audio, **toàn bộ độ dài**: 50,0 phút, 787 câu, V1–V4, 1 lần | `results/full_r1/` |
| L3 (`full_r2`, `full_r3`) | Lặp V2, V4 | **Thất bại** (hết credit Gemini, HTTP 402); thư mục giữ lại kèm `NOTES.md` |

Dữ liệu (audio mp3 tách từ video YouTube, tất cả tiếng Anh): `lec01` Crash Course CS #10 (9,4 phút), `lec02` CS #18 (13,6), `lec03` CS #29 (12,0), `lec04` Stanford CS229 Lecture 1, 15 phút đầu (15,0).
Link và ghi chú nằm trong `experiments/videos.json`; giấy phép chưa xác minh.

Script bổ sung (không sửa code app): `drift_analysis.py`, `check_full_length.py`, `aggregate_runs.py`, `sample_fidelity.py`.

## 3. Kết quả so sánh V1–V4

| Phương án | Δ TB (s) | % câu còn tràn | % R>1,3 sau | Gọi LLM |
|---|---|---|---|---|
| **Đợt 1** (603 câu, 10 phút đầu) | | | | |
| V1 một pha | 1,679 | 94,2 | 75,3 | 4 |
| V2 hai pha | 0,989 | 82,9 | 48,3 | 8 |
| V3 hai pha + tăng tốc | 0,318 | 48,1 | 18,6 | 8 |
| V4 đề xuất | 0,157 | 23,5 | 13,8 | 444 |
| **Đợt 2 `full_r1`** (787 câu, toàn bài) | | | | |
| V1 | 1,649 | 94,0 | 75,6 | 7 |
| V2 | 1,093 | 84,2 | 55,8 | 14 |
| V3 | 0,392 | 54,9 | 25,3 | 14 |
| V4 | 0,190 | 26,7 | 17,0 | 690 |

Xu hướng V1 → V4 giống nhau ở hai đợt. Khác biệt nhỏ giữa hai đợt (V4: 0,157 so với 0,190 s) chưa quy được cho nguyên nhân nào vì LLM không tất định và tập câu khác nhau; cần lặp lại mới biết độ dao động.
Phân bố nhánh V4 (`full_r1`): rút gọn 33,5%, tăng tốc 29,6%, chạm trần +30% (`capped`) 22,2%, đệm lặng 14,6%. Chi tiết trong `summary.md` của từng run.

## 4. Vấn đề chính: audio lồng tiếng dài hơn bản gốc và trễ cộng dồn

### 4.1. Số đo trên audio thật (`results/full_r1/check_full_length.md`)
Ghép lại audio của cả bài đúng cách pipeline ghép, đo bằng `audio_utils.measure_duration_sec`:

| Video | Phương án | Gốc (s) | Sau ghép (s) | Chênh | Trễ mốc câu TB / max (s) |
|---|---|---|---|---|---|
| lec01 | V2 | 566,0 | 695,14 | +22,8% | 66,7 / 127,7 |
| lec01 | V4 | 566,0 | 575,41 | +1,7% | 3,1 / 8,0 |
| lec02 | V2 | 815,1 | 1093,03 | +34,1% | 130,8 / 277,1 |
| lec02 | V4 | 815,1 | 833,39 | +2,2% | 8,1 / 17,5 |
| lec03 | V2 | 718,0 | 898,28 | +25,1% | 91,5 / 186,1 |
| lec03 | V4 | 718,0 | 761,50 | +6,1% | 7,8 / 22,1 |
| lec04 | V2 | 900,0 | 1063,54 | +18,2% | 72,1 / 164,0 |
| lec04 | V4 | 900,0 | 995,89 | +10,7% | 43,1 / 95,9 |

Không có đoạn 10 phút nào ghép ra đúng bằng khung (ví dụ `lec04` V4: 600 → 654,87 s và 300 → 341,01 s). Số đo này dùng file câu của thí nghiệm, chưa phải `final.mp3` thật trên server.

### 4.2. Cơ chế (đọc từ code)
Trong [dubbing_service.py:284](../../../app/services/dubbing_service.py#L284), khoảng lặng trước mỗi câu là `seg.start − prev_end` của **bản gốc**, cố định. Câu đọc dài hơn khung `T_orig` được chèn nguyên độ dài,
nên mọi câu sau bị đẩy lùi đúng phần dư và **không được bù lại**. Ở [dubbing_service.py:319-321](../../../app/services/dubbing_service.py#L319) khoảng đệm cuối đoạn là `max(0, chunk.end − prev_end)` — không bao giờ âm
nên không cắt bớt khi đoạn dài hơn; `concat_files` chỉ nối các đoạn, nên **độ trễ của đoạn này chuyển sang đoạn sau**. Chỉ số Δ = |t_final − t_orig| theo từng câu **không phản ánh** hiện tượng này vì nó không cộng dồn.

### 4.3. Vì sao ở video ngắn không thấy khác biệt
Độ trễ tích lũy theo số câu tràn, nên tỷ lệ với độ dài video: `lec01` (9,4 phút) chỉ lệch 9,4 s với V4, còn `lec04` (15 phút) lệch 96 s. Với video ~10 phút, vài giây trễ khó nhận ra bằng tai. Theo Thiện, các bài đã lồng tiếng sẵn trên hệ thống đều ngắn nên chưa lộ ra (chưa kiểm chứng trên `final.mp3` của server). Bài giảng dài (bài báo nói tối đa 180 phút) sẽ lệch nhiều hơn, nhưng **chưa đo** ở độ dài đó.

### 4.4. Mô phỏng hướng sửa (không tốn API)
Mô phỏng từ `segments.csv` và `asr_cache.json` của `full_r1`, giữ nguyên câu dịch và giọng đọc, chỉ đổi cách xếp: **câu i bắt đầu tại `max(mốc gốc, thời điểm câu trước kết thúc)`** thay vì chèn khoảng lặng tương đối.
Độ dài giọng đọc dùng độ dài thật (bỏ phần đệm lặng ở nhánh `pad`). Đây là **mô phỏng**, chưa phải audio thật.

| Video (V4) | Trễ mốc câu max hiện tại (đo thật) | Trễ max sau khi xếp theo mốc tuyệt đối (mô phỏng) | Trễ TB hiện tại → mô phỏng | % câu trễ >2 s hiện tại → mô phỏng |
|---|---|---|---|---|
| lec01 | 8,0 s | 2,7 s | 3,1 → 0,7 s | 61,1 → 0,8 |
| lec02 | 17,5 s | 10,4 s | 8,1 → 3,0 s | 93,5 → 50,3 |
| lec03 | 22,1 s | 5,6 s | 7,8 → 1,5 s | 85,1 → 29,8 |
| lec04 | 95,9 s | 18,5 s | 43,1 → 3,2 s | 94,1 → 40,7 |

Cải thiện lớn nhưng **không về 0**: những đoạn lời thoại dày không đủ khoảng lặng để bù thì vẫn trễ (V4 vẫn còn 22,2% câu chạm trần +30%). Với V2 (không rút gọn) mô phỏng vẫn trễ rất nhiều (max 79–265 s) — cho thấy cách xếp theo mốc tuyệt đối **không đủ nếu thiếu bước rút gọn/tăng tốc của V4**; hai thứ cần đi cùng nhau.
Lưu ý: vì file câu của thí nghiệm đã lưu (`--keep-audio`), **ghép lại theo cách mới không tốn API** — chỉ cần chạy lại phần ghép.

## 5. Vấn đề phụ: ASR trả mốc vượt hết audio (`lec03`)
Câu cuối `lec03` (seq 181, *"Thank you."*) có mốc 709,44 → 739,42 s trong khi audio chỉ dài 718,0 s (`t_orig` = 29,98 s). Pipeline không giới hạn mốc theo thời lượng audio, nên đoạn cuối bị đệm thêm khoảng 21 s.
Bỏ câu này thì chênh của `lec03` V4 ≈ 22 s (khớp ước lượng 22,09 s từ CSV). Gợi ý: giới hạn `start/end` của câu trong [0, thời lượng audio] và trong biên đoạn; bỏ câu có `start` ≥ thời lượng.

## 6. Vấn đề về dữ liệu
1. **Không có video kỹ năng mềm.** `videos.json` gắn `KyNangMem` cho `lec03` (The Internet) và `lec04` (Stanford CS229) nhưng nội dung là CNTT. Bài báo ghi thực nghiệm trên "CNTT và kỹ năng mềm". Cần thêm ≥ 2 bài kỹ năng mềm hoặc sửa lại mô tả.
2. **Chỉ có audio mp3**: không đo được độ khớp hình; muốn lồng tiếng thật trên web cần file `.mp4` (backend chỉ nhận `.mp4`, 1–180 phút).
3. **Giấy phép chưa xác minh** (3 bài Crash Course cùng một series nên đa dạng người nói thấp).
4. **Chỉ 1 lần chạy** đầy đủ, chưa biết độ dao động do LLM không tất định. Hướng dẫn mục 9.3 L3 yêu cầu tối thiểu 2 lần cho V4.
5. **L4 chưa chấm:** mẫu 50 câu rút gọn (seed 42) đã tạo (`results/full_r1/fidelity_sample.csv`), cần Sang và Thiện chấm độc lập. Ví dụ đợt 1: *"Thought Cafe."* rút thành *"Tư duy"* — chỉ là ví dụ, chưa kết luận.
6. **Số liệu server (S1–S5)** chưa lấy: cần phép của Sang, thông tin commit/model trên server, và danh sách job test cần loại.

## 7. Vấn đề vận hành
- **Credit Gemini đã hết** (HTTP 402) ngày 10/11. Key này nằm trong `lms_ai_worker`, container phục vụ cả hệ thống thật; **chưa kiểm tra** xem tính năng AI thật có đang lỗi không. Provider không phân biệt lỗi 402 với 5xx (log chỉ báo "network error"/"cooldown").
- **Chi phí ước tính** (từ billing AI Studio): ~109₫ mỗi lần gọi Gemini; một lượt V4 50 phút (~690 lần gọi) ≈ 75K₫. Nguyên nhân đơn giá cao chưa xác định (nghi token "suy nghĩ" ẩn vì code không đặt `thinkingBudget`; chưa kiểm chứng).
- **Máy đo dùng chung với hệ thống thật** (2 vCPU, 3,7 GiB RAM, còn ~1 GiB): số "giây xử lý trên phút video" ở local **không dùng làm số liệu vận hành**; chỉ dùng số từ server (S1).

## 8. Hướng đi để hoàn thiện bài

### Phương án A — Sửa pipeline rồi đo lại (đề xuất, nếu kịp)
- **Sửa:** xếp câu theo mốc tuyệt đối khi ghép (mục 4.4); giới hạn mốc ASR theo thời lượng audio (mục 5). Chỉ đụng phần ghép audio, **không đổi câu dịch, tốc độ đọc hay số lần gọi LLM** — nên bảng Δ/R/LLM ở mục 3 vẫn đúng.
- **Đo lại:** ghép lại từ file câu đã lưu bằng cách mới (không tốn API), chạy `check_full_length.py` để lấy số thật; sau đó lồng tiếng thật trên web bằng code đã sửa để có số server.
- **Ưu điểm:** câu "không tích lũy độ trễ" trong bài trở nên đúng một phần và có số đo chứng minh; kết quả mạnh hơn. **Rủi ro:** vẫn còn trễ ở đoạn dày lời (mô phỏng: max ~18 s ở `lec04`), nên bài vẫn cần ghi trung thực mức trễ còn lại; cần Sang sửa và chốt commit.
- Có thể đề xuất thêm (chưa thử): nếu cuối đoạn vẫn dài hơn khung, tăng tốc nhẹ cả đoạn hoặc buộc rút gọn mạnh hơn ở đoạn dày lời.

### Phương án B — Giữ nguyên code, sửa bài cho đúng với số đo
- Bỏ/đổi câu "thời lượng đúng bằng L … không tích lũy độ trễ" thành mô tả đúng cơ chế; báo cáo độ trễ cộng dồn đo được (mục 4.1) như một phát hiện và một hạn chế; thêm hướng phát triển "bù trễ khi ghép".
- **Ưu điểm:** ít việc, không cần đổi code. **Nhược điểm:** bài báo mô tả một hạn chế lớn của chính hệ thống; phản biện có thể hỏi vì sao không sửa.

### Cả hai phương án đều cần
1. Thêm chỉ số **trễ mốc câu / tổng thời lượng so với gốc** vào phần "Độ đo" (Δ theo câu không đủ).
2. Thêm 2 bài kỹ năng mềm hoặc sửa mô tả; xác minh giấy phép.
3. Chấm L4 (Sang, Thiện) và, nếu kịp, MOS (cần video gốc).
4. Lấy số liệu server S1–S3, S5 (cần phép của Sang).
5. Sang tự điền số vào `main.tex` sau khi kiểm tra lại (theo quy tắc nhóm).

## 9. Kế hoạch đến hạn 15/11 (đề xuất — cần Sang chỉnh)

| Ngày | Việc | Ai | Chi phí API ước tính |
|---|---|---|---|
| 11/11 | Đọc báo cáo, chọn phương án A hoặc B; chốt commit đo; cho phép S4 | Sang | – |
| 11/11 | Nạp credit Gemini; chọn 2 video kỹ năng mềm, tải 4 file mp4 | Thiện | ~150K₫ (nạp) |
| 12/11 | (A) Sửa phần ghép; ghép lại `full_r1` bằng cách mới, đo lại | Sang + Claude | 0 |
| 12/11 | Tạo khoá học tạm, upload 4 mp4, lồng tiếng sang `vi-VN` (1 lần); chạy script V1–V4 cho 2 bài kỹ năng mềm mới | Thiện + Claude | ~110–115K₫ |
| 13/11 | Lấy số liệu server (SQL chỉ đọc), đo trễ trên `final.mp3`; chấm L4 | Thiện, Sang | 0 |
| 14/11 | Cập nhật REPORT; Sang điền `main.tex`; MOS nếu kịp | Sang, Thiện | 0 |
| 15/11 | Rà soát, xoá `\todo`, nộp | Cả nhóm | – |

Bỏ L3 chạy riêng để tiết kiệm: job web trên `lec02`, `lec04` là lần chạy V4 thứ hai (so ở mức tổng thể: tỷ lệ rút gọn, tốc độ đọc, tổng thời lượng — không so được Δ từng câu). Cần Sang xác nhận cách này đủ cho bài.

## 10. Câu hỏi cần Sang trả lời
1. Chọn **A** (sửa ghép audio) hay **B** (giữ code, sửa bài)? Nếu A, ai sửa và commit nào là bản để đo?
2. Cho phép lồng tiếng thật trên hệ thống chạy (S4)? Dùng khoá học tạm của `instructor@lms.local` hay tài khoản khác? Sau khi xong có xoá không?
3. Thêm 2 bài kỹ năng mềm (kèm file mp4) hay đổi mô tả bài thành "lĩnh vực CNTT"?
4. Server đang chạy commit và model Gemini nào (S5)? Job nào là test cần loại khỏi S1? Các bài B1, B2 khoá Unity/Agent là link YouTube hay file upload, ngôn ngữ gốc là gì?
5. Có kiểm tra tác động của việc hết credit Gemini lên hệ thống thật chưa? Có muốn đặt `thinkingBudget` thấp cho lời gọi rút gọn để giảm chi phí không (việc này đổi chất lượng câu rút gọn, nên cần đo lại)?
6. Cách tiết kiệm ở mục 9 (không chạy L3 riêng) có đủ cho phản biện không?

## Phụ lục — Kiểm tra lại các con số
```bash
python NCKH/experiments/analyze.py NCKH/experiments/results/full_r1        # mục 3
python NCKH/experiments/drift_analysis.py NCKH/experiments/results/full_r1 # ước lượng trễ từ CSV
# trong container ai-worker, cần audio/ của run (không commit):
docker exec --user 1000:1001 -w /app lms_ai_worker python NCKH/experiments/check_full_length.py NCKH/experiments/results/full_r1 --variants V2,V4   # mục 4.1
```
Mô phỏng ở mục 4.4: `python NCKH/experiments/simulate_resync.py NCKH/experiments/results/full_r1 --variants V2,V4` (không gọi API; cần `.cache/<id>/asr_cache.json`, không commit — chạy được trên máy đã chạy run).
Kết quả đã ghi ở `results/full_r1/simulate_resync.md/json`. Thuật toán: `onset = max(start, thời điểm câu trước kết thúc)`, độ dài giọng đọc = `t_final` (nhánh `pad` dùng `t_tts_default`), trễ = `onset − start`.
