# Tóm tắt thực nghiệm

Run: `v3_r1_merged`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Dịch không ràng buộc, tốc độ mặc định | 780 | 1.893 | 1.728 | 3.776 | 96.9 | 82.8 | 7 | 780 |
| Dịch theo ngân sách thời lượng, tốc độ mặc định | 780 | 1.248 | 1.22 | 2.656 | 90.5 | 63.7 | 7 | 780 |
| Thêm giới hạn ký tự + atempo, không rút gọn | 780 | 0.288 | 0.0 | 1.112 | 46.5 | 23.2 | 7 | 780 |
| Đề xuất (đầy đủ) | 780 | 0.185 | 0.0 | 0.961 | 30.4 | 19.6 | 20 | 1034 |

### Dòng LaTeX cho Bảng tab:results

```latex
Dịch không ràng buộc, tốc độ mặc định & 1.89 & 82.8\% & 7 \\
Dịch theo ngân sách thời lượng, tốc độ mặc định & 1.25 & 63.7\% & 7 \\
Thêm giới hạn ký tự + atempo, không rút gọn & 0.29 & 23.2\% & 7 \\
Đề xuất (đầy đủ) & 0.18 & 19.6\% & 20 \\
```

## Phân bố nhánh xử lý

```json
{
 "V1": {
  "none": {
   "n": 756,
   "pct": 96.9
  },
  "pad": {
   "n": 24,
   "pct": 3.1
  },
  "_R_zones": {
   "R<=1.0": 3.1,
   "1.0<R<=1.3": 14.1,
   "R>1.3": 82.8
  }
 },
 "V2": {
  "none": {
   "n": 711,
   "pct": 91.2
  },
  "pad": {
   "n": 69,
   "pct": 8.8
  },
  "_R_zones": {
   "R<=1.0": 8.8,
   "1.0<R<=1.3": 27.4,
   "R>1.3": 63.7
  }
 },
 "V3": {
  "capped": {
   "n": 375,
   "pct": 48.1
  },
  "speedup": {
   "n": 229,
   "pct": 29.4
  },
  "pad": {
   "n": 176,
   "pct": 22.6
  },
  "_R_zones": {
   "R<=1.0": 22.6,
   "1.0<R<=1.3": 29.4,
   "R>1.3": 48.1
  }
 },
 "V4": {
  "capped": {
   "n": 240,
   "pct": 30.8
  },
  "speedup": {
   "n": 229,
   "pct": 29.4
  },
  "pad": {
   "n": 179,
   "pct": 22.9
  },
  "summarize": {
   "n": 132,
   "pct": 16.9
  },
  "_R_zones": {
   "R<=1.0": 22.6,
   "1.0<R<=1.3": 29.4,
   "R>1.3": 48.1
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
 "asr_sec_per_min": 0.7,
 "translate_sec_per_min": 4.87,
 "tts_default_sec_per_min": 8.2,
 "v4_adaptive_sec_per_min": 10.26,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```