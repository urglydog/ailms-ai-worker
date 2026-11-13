# Tóm tắt thực nghiệm

Run: `post_fix_r1`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Dịch một pha, tốc độ mặc định | 787 | 1.669 | 1.544 | 3.4 | 95.2 | 75.3 | 7 | 787 |
| Dịch hai pha, tốc độ mặc định | 787 | 0.996 | 0.912 | 2.524 | 83.5 | 50.7 | 14 | 787 |
| Hai pha + tăng tốc độ đọc | 787 | 0.357 | 0.048 | 1.308 | 49.8 | 23.8 | 14 | 666 |
| Đề xuất (đầy đủ) | 787 | 0.216 | 0.012 | 1.108 | 27.6 | 19.9 | 286 | 1678 |

### Dòng LaTeX cho Bảng tab:results

```latex
Dịch một pha, tốc độ mặc định & 1.67 & 75.3\% & 7 \\
Dịch hai pha, tốc độ mặc định & 1.00 & 50.7\% & 14 \\
Hai pha + tăng tốc độ đọc & 0.36 & 23.8\% & 14 \\
Đề xuất (đầy đủ) & 0.22 & 19.9\% & 286 \\
```

## Phân bố nhánh xử lý

```json
{
 "V1": {
  "none": {
   "n": 750,
   "pct": 95.3
  },
  "pad": {
   "n": 37,
   "pct": 4.7
  },
  "_R_zones": {
   "R<=1.0": 4.7,
   "1.0<R<=1.3": 19.9,
   "R>1.3": 75.3
  }
 },
 "V2": {
  "none": {
   "n": 666,
   "pct": 84.6
  },
  "pad": {
   "n": 121,
   "pct": 15.4
  },
  "_R_zones": {
   "R<=1.0": 15.4,
   "1.0<R<=1.3": 33.9,
   "R>1.3": 50.7
  }
 },
 "V3": {
  "capped": {
   "n": 399,
   "pct": 50.7
  },
  "speedup": {
   "n": 267,
   "pct": 33.9
  },
  "pad": {
   "n": 121,
   "pct": 15.4
  },
  "_R_zones": {
   "R<=1.0": 15.4,
   "1.0<R<=1.3": 33.9,
   "R>1.3": 50.7
  }
 },
 "V4": {
  "speedup": {
   "n": 449,
   "pct": 57.1
  },
  "summarize": {
   "n": 190,
   "pct": 24.1
  },
  "pad": {
   "n": 124,
   "pct": 15.8
  },
  "capped": {
   "n": 24,
   "pct": 3.0
  },
  "_R_zones": {
   "R<=1.0": 15.4,
   "1.0<R<=1.3": 33.9,
   "R>1.3": 50.7
  }
 }
}
```

## Thời gian (local)

```json
{
 "n_videos": 4,
 "total_minutes_source": 50.0,
 "total_minutes": 50.0,
 "asr_sec_per_min": null,
 "translate_sec_per_min": 10.42,
 "tts_default_sec_per_min": 48.07,
 "v4_adaptive_sec_per_min": 72.2,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```