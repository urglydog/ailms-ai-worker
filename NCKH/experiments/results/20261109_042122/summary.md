# Tóm tắt thực nghiệm

Run: `20261109_042122`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Dịch một pha, tốc độ mặc định | 603 | 1.679 | 1.556 | 3.46 | 94.2 | 75.3 | 4 | 603 |
| Dịch hai pha, tốc độ mặc định | 603 | 0.989 | 0.908 | 2.512 | 82.9 | 48.3 | 8 | 603 |
| Hai pha + tăng tốc độ đọc | 603 | 0.318 | 0.044 | 1.128 | 48.1 | 18.6 | 8 | 504 |
| Đề xuất (đầy đủ) | 603 | 0.157 | 0.016 | 0.908 | 23.5 | 13.8 | 444 | 1507 |

### Dòng LaTeX cho Bảng tab:results

```latex
Dịch một pha, tốc độ mặc định & 1.68 & 75.3\% & 4 \\
Dịch hai pha, tốc độ mặc định & 0.99 & 48.3\% & 8 \\
Hai pha + tăng tốc độ đọc & 0.32 & 18.6\% & 8 \\
Đề xuất (đầy đủ) & 0.16 & 13.8\% & 444 \\
```

## Phân bố nhánh xử lý

```json
{
 "V1": {
  "none": {
   "n": 570,
   "pct": 94.5
  },
  "pad": {
   "n": 33,
   "pct": 5.5
  },
  "_R_zones": {
   "R<=1.0": 5.5,
   "1.0<R<=1.3": 19.4,
   "R>1.3": 75.1
  }
 },
 "V2": {
  "none": {
   "n": 504,
   "pct": 83.6
  },
  "pad": {
   "n": 99,
   "pct": 16.4
  },
  "_R_zones": {
   "R<=1.0": 16.4,
   "1.0<R<=1.3": 35.3,
   "R>1.3": 48.3
  }
 },
 "V3": {
  "capped": {
   "n": 291,
   "pct": 48.3
  },
  "speedup": {
   "n": 213,
   "pct": 35.3
  },
  "pad": {
   "n": 99,
   "pct": 16.4
  },
  "_R_zones": {
   "R<=1.0": 16.4,
   "1.0<R<=1.3": 35.3,
   "R>1.3": 48.3
  }
 },
 "V4": {
  "speedup": {
   "n": 211,
   "pct": 35.0
  },
  "summarize": {
   "n": 179,
   "pct": 29.7
  },
  "capped": {
   "n": 113,
   "pct": 18.7
  },
  "pad": {
   "n": 100,
   "pct": 16.6
  },
  "_R_zones": {
   "R<=1.0": 16.4,
   "1.0<R<=1.3": 35.3,
   "R>1.3": 48.3
  }
 }
}
```

## Thời gian (local)

```json
{
 "n_videos": 4,
 "total_minutes": 50.0,
 "asr_sec_per_min": 0.44,
 "translate_sec_per_min": 7.67,
 "tts_default_sec_per_min": 41.11,
 "v4_adaptive_sec_per_min": 79.44,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```