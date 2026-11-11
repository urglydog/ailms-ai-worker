# Độ trễ cộng dồn ước lượng — run `full_r2`

_Ước lượng từ `segments.csv` (mô hình trong `drift_analysis.py`); chưa phải số đo trên audio thật._

## Theo phương án (trung bình/lớn nhất trên các video)

| Phương án | Trễ cuối video TB (s) | Trễ cuối video max (s) | Trễ cuối đoạn TB (s) | Trễ cuối đoạn max (s) |
|---|---|---|---|---|
| V2 | 171.28 | 171.28 | 171.28 | 171.28 |
| V4 | 9.79 | 9.79 | 9.79 | 9.79 |

## Theo video

| Phương án | Video | Đoạn | Trễ cuối video (s) | Trễ cuối đoạn max (s) | % câu trễ cộng dồn >1 s | >2 s |
|---|---|---|---|---|---|---|
| V2 | lec01 | 1 | 171.28 | 171.28 | 98.5 | 97.7 |
| V4 | lec01 | 1 | 9.79 | 9.79 | 68.7 | 67.9 |
