# Tóm tắt thực nghiệm

Run: `smoke_real2`

## Bảng so sánh phương án

| Phương án | n câu | Δ TB (s) | Δ trung vị | Δ p95 | % câu còn tràn | % R>1.3 sau | LLM | TTS |
|---|---|---|---|---|---|---|---|---|
| Dịch không ràng buộc, tốc độ mặc định | 131 | 2.147 | 2.116 | 3.64 | 100.0 | 85.5 | 1 | 131 |
| Dịch theo ngân sách thời lượng, tốc độ mặc định | 131 | 1.269 | 1.224 | 2.628 | 93.9 | 55.7 | 1 | 131 |
| Thêm giới hạn ký tự + atempo, không rút gọn | 131 | 0.325 | 0.149 | 1.232 | 55.0 | 15.3 | 1 | 131 |
| Đề xuất (đầy đủ) | 131 | 0.313 | 0.132 | 1.204 | 53.4 | 15.3 | 2 | 131 |

### Dòng LaTeX cho Bảng tab:results

```latex
Dịch không ràng buộc, tốc độ mặc định & 2.15 & 85.5\% & 1 \\
Dịch theo ngân sách thời lượng, tốc độ mặc định & 1.27 & 55.7\% & 1 \\
Thêm giới hạn ký tự + atempo, không rút gọn & 0.33 & 15.3\% & 1 \\
Đề xuất (đầy đủ) & 0.31 & 15.3\% & 2 \\
```

## Phân bố nhánh xử lý

```json
{
 "V1": {
  "none": {
   "n": 131,
   "pct": 100.0
  },
  "_R_zones": {
   "R<=1.0": 0.0,
   "1.0<R<=1.3": 14.5,
   "R>1.3": 85.5
  }
 },
 "V2": {
  "none": {
   "n": 126,
   "pct": 96.2
  },
  "pad": {
   "n": 5,
   "pct": 3.8
  },
  "_R_zones": {
   "R<=1.0": 3.8,
   "1.0<R<=1.3": 40.5,
   "R>1.3": 55.7
  }
 },
 "V3": {
  "capped": {
   "n": 73,
   "pct": 55.7
  },
  "speedup": {
   "n": 53,
   "pct": 40.5
  },
  "pad": {
   "n": 5,
   "pct": 3.8
  },
  "_R_zones": {
   "R<=1.0": 3.8,
   "1.0<R<=1.3": 40.5,
   "R>1.3": 55.7
  }
 },
 "V4": {
  "capped": {
   "n": 71,
   "pct": 54.2
  },
  "speedup": {
   "n": 54,
   "pct": 41.2
  },
  "pad": {
   "n": 6,
   "pct": 4.6
  },
  "_R_zones": {
   "R<=1.0": 3.8,
   "1.0<R<=1.3": 40.5,
   "R>1.3": 55.7
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
 "translate_sec_per_min": 4.5,
 "tts_default_sec_per_min": 7.4,
 "v4_adaptive_sec_per_min": 8.64,
 "note": "Thời gian local, chạy tuần tự từng câu; số liệu triển khai thật lấy từ server_job_stats."
}
```