# Tóm tắt thực nghiệm

Run: `v3_r2`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Đề xuất (đầy đủ) | 780 | 0.194 | 0.0 | 1.072 | 26.4 | 19.0 | 21 | 845 |

### Dòng LaTeX cho Bảng tab:results

```latex
Đề xuất (đầy đủ) & 0.19 & 19.0\% & 21 \\
```

## Phân bố nhánh xử lý

```json
{
 "V4": {
  "pad": {
   "n": 356,
   "pct": 45.6
  },
  "capped": {
   "n": 212,
   "pct": 27.2
  },
  "speedup": {
   "n": 178,
   "pct": 22.8
  },
  "summarize": {
   "n": 34,
   "pct": 4.4
  },
  "_R_zones": {
   "R<=1.0": 46.0,
   "1.0<R<=1.3": 26.5,
   "R>1.3": 27.4
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
 "translate_sec_per_min": 1.7,
 "tts_default_sec_per_min": 0.0,
 "v4_adaptive_sec_per_min": 8.93,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```