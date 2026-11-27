# Tóm tắt thực nghiệm

Run: `v3_r1`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Dịch không ràng buộc, tốc độ mặc định | 649 | 1.838 | 1.672 | 3.792 | 96.3 | 82.4 | 6 | 649 |
| Dịch theo ngân sách thời lượng, tốc độ mặc định | 649 | 1.211 | 1.2 | 2.652 | 89.2 | 63.8 | 6 | 649 |
| Thêm giới hạn ký tự + atempo, không rút gọn | 649 | 0.314 | 0.088 | 1.128 | 51.6 | 26.3 | 6 | 649 |
| Đề xuất (đầy đủ) | 649 | 0.204 | 0.0 | 0.97 | 34.4 | 22.3 | 17 | 876 |

### Dòng LaTeX cho Bảng tab:results

```latex
Dịch không ràng buộc, tốc độ mặc định & 1.84 & 82.4\% & 6 \\
Dịch theo ngân sách thời lượng, tốc độ mặc định & 1.21 & 63.8\% & 6 \\
Thêm giới hạn ký tự + atempo, không rút gọn & 0.31 & 26.3\% & 6 \\
Đề xuất (đầy đủ) & 0.20 & 22.3\% & 17 \\
```

## Phân bố nhánh xử lý

```json
{
 "V1": {
  "none": {
   "n": 625,
   "pct": 96.3
  },
  "pad": {
   "n": 24,
   "pct": 3.7
  },
  "_R_zones": {
   "R<=1.0": 3.7,
   "1.0<R<=1.3": 13.9,
   "R>1.3": 82.4
  }
 },
 "V2": {
  "none": {
   "n": 583,
   "pct": 89.8
  },
  "pad": {
   "n": 66,
   "pct": 10.2
  },
  "_R_zones": {
   "R<=1.0": 10.2,
   "1.0<R<=1.3": 26.0,
   "R>1.3": 63.8
  }
 },
 "V3": {
  "capped": {
   "n": 346,
   "pct": 53.3
  },
  "speedup": {
   "n": 184,
   "pct": 28.4
  },
  "pad": {
   "n": 119,
   "pct": 18.3
  },
  "_R_zones": {
   "R<=1.0": 18.3,
   "1.0<R<=1.3": 28.4,
   "R>1.3": 53.3
  }
 },
 "V4": {
  "capped": {
   "n": 224,
   "pct": 34.5
  },
  "speedup": {
   "n": 187,
   "pct": 28.8
  },
  "summarize": {
   "n": 119,
   "pct": 18.3
  },
  "pad": {
   "n": 119,
   "pct": 18.3
  },
  "_R_zones": {
   "R<=1.0": 18.3,
   "1.0<R<=1.3": 28.4,
   "R>1.3": 53.3
  }
 }
}
```

## Thời gian (local)

```json
{
 "n_videos": 3,
 "total_minutes_source": 40.6,
 "total_minutes": 40.6,
 "asr_sec_per_min": 0.7,
 "translate_sec_per_min": 4.69,
 "tts_default_sec_per_min": 8.34,
 "v4_adaptive_sec_per_min": 10.65,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```