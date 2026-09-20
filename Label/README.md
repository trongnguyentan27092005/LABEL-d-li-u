# ViRPM Annotation App

Ứng dụng gán nhãn cục bộ, không hiển thị nhãn có sẵn, dự đoán mô hình hoặc
nhãn của người gán khác. Một đơn vị I2I là **một ảnh review** đối chiếu với
**toàn bộ tập ảnh sản phẩm**. T2T được ghi kèm theo từng đơn vị ảnh; khi phân
tích cần khử trùng lặp T2T theo `review_id` trong từng người gán.

Từ thư mục gốc dự án, chạy:

```powershell
python Label/app.py --input artifacts/splits/core.csv --subset core-1000
```

Sau đó mở `http://127.0.0.1:8765` trong trình duyệt. Có thể dùng một tập khác:

```powershell
python Label/app.py --input artifacts/splits/diagnostic.csv --subset diagnostic-300 --port 8766
```

## Cho người gán nhãn trên cùng mạng Wi-Fi/LAN

Trên máy đang chứa dữ liệu, mở PowerShell ở thư mục dự án và chạy:

```powershell
.\Label\run_lan.ps1
```

Tìm IPv4 của máy đó bằng `ipconfig`, rồi gửi cho người gán đường dẫn
`http://<IPv4>:8765`. Họ chỉ cần trình duyệt; không cần có dữ liệu ViRPM trên
máy của họ. Giữ cửa sổ PowerShell này mở trong suốt phiên gán nhãn.

Chế độ LAN không có cơ chế tài khoản/mật khẩu; chỉ dùng trên mạng tin cậy. Để
đưa app ra Internet cần một máy chủ riêng có kiểm soát truy cập và nơi lưu ảnh
ViRPM, không nên mở trực tiếp cổng máy cá nhân ra Internet.

Mỗi người nhập tên/mã riêng. App lưu nối tiếp, có timestamp, tại:

```text
Label/data/annotations/<ten_nguoi_gan>.jsonl
```

Nếu người gán mở lại với cùng tên và cùng tập đầu vào, app sẽ tự tiếp tục từ
đơn vị chưa hoàn thành. Không chỉnh sửa trực tiếp các tệp JSONL trong khi app
đang chạy.

Trường `reason` bắt buộc cho N5, N6, M5, M6 và mọi mẫu `ambiguous`, đúng theo
hướng dẫn gán nhãn phiên bản 2.
