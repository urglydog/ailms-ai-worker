# Hướng dẫn cấu hình Modal để tách nhạc nền khi lồng tiếng

**Mục đích:** giữ lại nhạc nền của video gốc trong bản lồng tiếng.
- Worker gửi audio gốc lên hàm Demucs chạy trên GPU của Modal, nhận về 2 phần: nhạc nền và giọng gốc.
- Nhạc nền được trộn dưới giọng lồng tiếng, giữ nguyên âm lượng gốc.
- Giọng lồng tiếng được chỉnh to bằng giọng gốc.
- Code: `app/services/background_music.py` và `modal_apps/demucs_separator.py`.

Chỉ cần **một tài khoản Modal** (của người trả phí GPU) và **một cặp token**. Cùng một cặp token dùng được cho cả máy local lẫn server.

---

## 1. Người sở hữu tài khoản Modal: đăng ký và lấy token

1. Vào https://modal.com → **Sign up**. Nên đăng nhập bằng GitHub.
2. **Thêm phương thức thanh toán** ở dòng thông báo "Add payment method" trên trang chính, hoặc vào Settings → Billing.
   - **Bắt buộc:** chưa có thẻ thì Modal không cho chạy GPU (lỗi `Please add a payment method to use T4 GPU functions`).
   - Gói Starter vẫn miễn phí 30 USD mỗi tháng, thẻ chỉ bị trừ khi dùng vượt mức đó.
3. Tạo token: **Settings** (biểu tượng bánh răng) → **API Tokens** → **New Token**. Nên đặt tên là `lms-ai-worker`.
4. Modal hiện **một lần duy nhất** 2 giá trị sau. Sao chép lại ngay:
   - **Token ID:** dạng `ak-xxxxxxxx`.
   - **Token Secret:** dạng `as-xxxxxxxx`.

> Không cần dùng trang **Endpoints**. Trang đó để chạy các model LLM có sẵn như Kimi, Qwen hay Gemma, không liên quan tới việc tách nhạc.

---

> **Người sở hữu tài khoản chỉ cần làm bước 1**, rồi gửi riêng 2 giá trị token cho nhóm dev. Từ bước 2 trở đi do nhóm dev làm.

## 2. Deploy hàm tách nhạc lên tài khoản đó (nhóm dev làm một lần)

Worker tìm hàm tên `lms-demucs` **trong đúng workspace mà token thuộc về**, nên hàm phải được deploy bằng chính token nhận được ở bước 1.

Điền token vào `project/ai-worker/.env` (xem mục 3), rồi chạy trong PowerShell tại `project/ai-worker`:
```powershell
$env:MODAL_TOKEN_ID = "ak-..."
$env:MODAL_TOKEN_SECRET = "as-..."
py -m modal deploy modal_apps/demucs_separator.py
```
Nếu người sở hữu tài khoản muốn tự deploy thì chạy `python -m modal setup` để đăng nhập, rồi chạy lệnh deploy ở trên.

**Lưu ý khi deploy:**
- **Không** đặt `DEMUCS_GPU=none`. Biến đó chỉ dùng để chạy thử bằng CPU khi chưa có thẻ.
- Mặc định hàm chạy trên GPU **T4**. Muốn đổi loại GPU thì đặt `DEMUCS_GPU=L4` trước khi deploy.
- Deploy thành công sẽ hiện dòng `✓ App deployed`. Trên trang Modal, mục **Apps** sẽ có `lms-demucs` ở trạng thái *deployed*.
- Chỉ cần deploy lại khi sửa file `modal_apps/demucs_separator.py`. Thêm máy mới hay đổi server **không cần deploy lại**.

---

## 3. Các biến cần có trong `project/ai-worker/.env` (local và server giống nhau)

```
# Bật tách nhạc nền (để trống = tắt, bản lồng tiếng chỉ có giọng như cũ)
BGM_SEPARATION=modal

# Token Modal ở bước 1 — KHÔNG commit, KHÔNG gửi qua chat nhóm
MODAL_TOKEN_ID=ak-...
MODAL_TOKEN_SECRET=as-...

# Không bắt buộc (đã có mặc định)
BGM_MODAL_APP=lms-demucs      # đổi nếu deploy với tên app khác
BGM_MUSIC_VOLUME=1.0          # 1.0 = giữ nguyên âm lượng nhạc gốc
BGM_DUCKING=false             # true = tự hạ nhạc khi có lời (chỉ bật nếu nghe thấy giọng gốc sót trong nhạc)
BGM_WAIT_TIMEOUT_SEC=600      # chờ tách nhạc tối đa; quá hạn thì chunk đó không có nhạc nền
```

**Vì sao đặt trong `.env` mà không phải Dockerfile:**
- `be/docker-compose.yml` đã nạp toàn bộ file này vào container worker (`env_file: ../ai-worker/.env`).
- Thư viện `modal`, đã có trong `requirements-app.txt`, tự đọc `MODAL_TOKEN_ID` và `MODAL_TOKEN_SECRET`.
- Ghi token vào Dockerfile thì token sẽ nằm luôn trong image, ai có image cũng đọc được.

---

## 4. Áp dụng và kiểm tra

1. **Tạo lại container** để nạp `.env` mới. Lệnh `restart` **không** nạp lại `env_file`. Chạy tại `project/be`:
   ```bash
   docker compose up -d --build ai-worker
   ```
2. Kiểm tra worker có thấy hàm trên Modal không:
   ```bash
   docker exec lms_ai_worker python -c "import modal; modal.Function.from_name('lms-demucs','separate').hydrate(); print('modal ok')"
   ```
3. Bấm lồng tiếng một bài có nhạc nền, rồi xem log của worker:
   ```bash
   docker logs -f lms_ai_worker
   ```
   Log cần có các dòng:
   - `BGM tach nhac xong: tren Modal ...s`: thời gian tách trên GPU.
   - `BGM do to: ... -> chinh ... dB`: mức chỉnh độ to giọng lồng tiếng.
   - `BGM tron nhac chunk ...`: đã trộn nhạc.

   Nếu thấy `BGM tach nhac that bai`, kiểm tra lại token, việc app đã được deploy chưa, và tài khoản đã thêm thẻ chưa. Khi bước này lỗi, job **vẫn lồng tiếng bình thường**, chỉ là không có nhạc nền.

---

## 5. Chi phí và bảo mật

- **Phí:** tính theo số giây GPU chạy, trừ vào 30 USD miễn phí mỗi tháng trước. Một bài khoảng 10 phút ước tính chỉ vài cent; con số này chưa đo trên GPU thật. Theo dõi ở mục **Credits** trên Modal.
- **Thời gian (đo trên CPU khi chưa có thẻ):** tách một bài 6–9 phút mất khoảng 120–185 s. Trên GPU dự kiến nhanh hơn nhiều; cần đo lại sau khi bật GPU.
- **Token có toàn quyền** trên workspace Modal đó:
  - Chỉ gửi riêng tư.
  - Bị lộ thì xóa token ở Settings → API Tokens, tạo token mới rồi cập nhật lại `.env` ở mọi máy.
- **Tắt tính năng:** để trống `BGM_SEPARATION` rồi tạo lại container. Không cần sửa code.
