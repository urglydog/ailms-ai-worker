# Tóm tắt thực nghiệm

Run: `full_r2`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Dịch hai pha, tốc độ mặc định | 131 | 1.308 | 1.236 | 2.96 | 91.6 | 56.5 | 2 | 131 |
| Đề xuất (đầy đủ) | 131 | 0.08 | 0.016 | 0.648 | 13.0 | 5.3 | 101 | 338 |

### Dòng LaTeX cho Bảng tab:results

```latex
Dịch hai pha, tốc độ mặc định & 1.31 & 56.5\% & 2 \\
Đề xuất (đầy đủ) & 0.08 & 5.3\% & 101 \\
```

## Phân bố nhánh xử lý

```json
{
 "V2": {
  "none": {
   "n": 120,
   "pct": 91.6
  },
  "pad": {
   "n": 11,
   "pct": 8.4
  },
  "_R_zones": {
   "R<=1.0": 8.4,
   "1.0<R<=1.3": 35.1,
   "R>1.3": 56.5
  }
 },
 "V4": {
  "summarize": {
   "n": 56,
   "pct": 42.7
  },
  "speedup": {
   "n": 46,
   "pct": 35.1
  },
  "capped": {
   "n": 18,
   "pct": 13.7
  },
  "pad": {
   "n": 11,
   "pct": 8.4
  },
  "_R_zones": {
   "R<=1.0": 8.4,
   "1.0<R<=1.3": 35.1,
   "R>1.3": 56.5
  }
 }
}
```

## Thời gian (local)

```json
{
 "n_videos": 1,
 "total_minutes_source": 9.4,
 "total_minutes": 9.4,
 "asr_sec_per_min": null,
 "translate_sec_per_min": 10.04,
 "tts_default_sec_per_min": 21.51,
 "v4_adaptive_sec_per_min": 102.24,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```