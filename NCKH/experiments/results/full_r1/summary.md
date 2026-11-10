# Tóm tắt thực nghiệm

Run: `full_r1`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Dịch một pha, tốc độ mặc định | 787 | 1.649 | 1.544 | 3.46 | 94.0 | 75.6 | 7 | 787 |
| Dịch hai pha, tốc độ mặc định | 787 | 1.093 | 1.024 | 2.632 | 84.2 | 55.8 | 14 | 787 |
| Hai pha + tăng tốc độ đọc | 787 | 0.392 | 0.144 | 1.328 | 54.9 | 25.3 | 14 | 677 |
| Đề xuất (đầy đủ) | 787 | 0.19 | 0.016 | 0.916 | 26.7 | 17.0 | 690 | 2097 |

### Dòng LaTeX cho Bảng tab:results

```latex
Dịch một pha, tốc độ mặc định & 1.65 & 75.6\% & 7 \\
Dịch hai pha, tốc độ mặc định & 1.09 & 55.8\% & 14 \\
Hai pha + tăng tốc độ đọc & 0.39 & 25.3\% & 14 \\
Đề xuất (đầy đủ) & 0.19 & 17.0\% & 690 \\
```

## Phân bố nhánh xử lý

```json
{
 "V1": {
  "none": {
   "n": 743,
   "pct": 94.4
  },
  "pad": {
   "n": 44,
   "pct": 5.6
  },
  "_R_zones": {
   "R<=1.0": 5.6,
   "1.0<R<=1.3": 18.8,
   "R>1.3": 75.6
  }
 },
 "V2": {
  "none": {
   "n": 677,
   "pct": 86.0
  },
  "pad": {
   "n": 110,
   "pct": 14.0
  },
  "_R_zones": {
   "R<=1.0": 14.0,
   "1.0<R<=1.3": 30.2,
   "R>1.3": 55.8
  }
 },
 "V3": {
  "capped": {
   "n": 439,
   "pct": 55.8
  },
  "speedup": {
   "n": 238,
   "pct": 30.2
  },
  "pad": {
   "n": 110,
   "pct": 14.0
  },
  "_R_zones": {
   "R<=1.0": 14.0,
   "1.0<R<=1.3": 30.2,
   "R>1.3": 55.8
  }
 },
 "V4": {
  "summarize": {
   "n": 264,
   "pct": 33.5
  },
  "speedup": {
   "n": 233,
   "pct": 29.6
  },
  "capped": {
   "n": 175,
   "pct": 22.2
  },
  "pad": {
   "n": 115,
   "pct": 14.6
  },
  "_R_zones": {
   "R<=1.0": 14.0,
   "1.0<R<=1.3": 30.2,
   "R>1.3": 55.8
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
 "asr_sec_per_min": 0.62,
 "translate_sec_per_min": 10.96,
 "tts_default_sec_per_min": 46.84,
 "v4_adaptive_sec_per_min": 126.17,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```