# SpotAI-Review — VS Code Extension (Windows x64)

Phân tích mã nguồn Python và Java trong VS Code với backend tích hợp sẵn. Bản
`1.1.2` chạy sau khi cài `.vsix`, không yêu cầu cài Python, chạy server hay
khai báo đường dẫn backend.

## Cài đặt và sử dụng

1. Trong VS Code mở **Extensions → … → Install from VSIX…** và chọn
   `spotai-review-1.1.2.vsix`.
2. Mở thư mục dự án Python/Java bất kỳ.
3. Dùng Command Palette (`Ctrl+Shift+P`) để chạy **SpotAI: Open Review Dashboard**.
   Backend tự khởi động và dashboard mở ở panel bên cạnh.
4. Trong tệp `.py` hoặc `.java`, chọn đoạn mã và chạy **SpotAI: Review Selected
   Snippet** từ menu chuột phải hoặc Command Palette. **SpotAI: Analyze Entire
   Current File** xử lý toàn bộ tệp. Hai lệnh này mở panel **SpotAI Code Review**
   với tổng số issues, Quality Gate, metrics, vị trí lỗi và đề xuất refactoring.
   Nhấn **Go to line** ở mỗi issue để quay tới dòng mã liên quan. Lệnh **Open
   Review Dashboard** mở giao diện Web dành cho repository và Playground.

Nếu đã cài phiên bản cũ, cài `spotai-review-1.1.2.vsix` và chạy **Developer:
Reload Window** trong VS Code để kích hoạt bản cập nhật.

**SpotAI: Start Local Web Server** là lệnh bổ sung để chủ động khởi động backend.
Các lệnh phân tích và dashboard tự thực hiện thao tác này khi cần.

Extension dùng một cổng `127.0.0.1` trống mỗi lần khởi động. Tệp tải lên,
cache AI và báo cáo được ghi trong thư mục lưu trữ riêng của extension do VS Code
cấp. Phân tích repository cục bộ trong dashboard được giới hạn theo workspace
đang mở. Để phân tích thư mục khác, hãy mở thư mục đó bằng VS Code.

Phân tích tĩnh và đề xuất fallback hoạt động offline. AI qua nhà cung cấp cloud
vẫn yêu cầu API key/kết nối nếu muốn sử dụng.

## Cấu hình nâng cao

`spotai.serverUrl` mặc định để trống, nghĩa là sử dụng backend tích hợp. Có thể
đặt một HTTP(S) origin, ví dụ `http://127.0.0.1:8000`, để kết nối một backend
Web đã chạy sẵn. Extension kiểm tra endpoint `/api/health`.

Nếu gặp lỗi khởi động, mở **View → Output → SpotAI Backend** để xem log rồi
chạy lại **SpotAI: Open Review Dashboard**. Gói này hiện hỗ trợ Windows x64.

## Build từ mã nguồn (chỉ dành cho nhóm phát triển)

Máy đóng gói cần Windows x64, Python 3.11+, Node.js/npm, các dependency trong
`requirements.txt` và PyInstaller:

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
npm test --prefix vscode-extension
npm run package --prefix vscode-extension
```

Lệnh `package` tạo executable Python ở `vscode-extension/backend/` và VSIX ở
`vscode-extension/spotai-review-1.1.2.vsix`. Máy nhận VSIX không cần các công
cụ build. Thư mục backend và build trung gian được bỏ qua bởi Git.
