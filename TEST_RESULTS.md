# Kết quả kiểm thử SpotAI-Review

Ngày kiểm tra gần nhất: **20/11/2026**. Môi trường: **Windows x64, Python 3.11.9, Node.js/npm, PowerShell, Microsoft Edge và VS Code 1.147.0**.

## 1. Kết quả thực thi

| Thành phần | Lệnh kiểm tra | Kết quả |
| --- | --- | --- |
| Python unit, CLI, phân tích, bảo mật, Web/API | `python -m unittest discover -s tests -p 'test_*.py' -v` | **52/52 PASS, 0 skip** |
| Python syntax/import compilation | `python -m compileall -q src spotai_cli.py evaluate_benchmarks.py tests` | **PASS** |
| VS Code extension, kiểm thử mock | `npm test --prefix vscode-extension` | **PASS** — đăng ký command, phân tích snippet/tệp, CSP, retry/offline và khởi chạy backend |
| Tạo báo cáo và số liệu mẫu | `python evaluate_benchmarks.py` | **PASS** — đã sinh JSON, SARIF, HTML cho ba repository |
| Đóng gói extension tích hợp backend | `npm run package --prefix vscode-extension` | **PASS** — sinh `spotai-review-1.1.2.vsix` (15.460.402 byte), chứa backend `spotai_backend.exe`; ZIP CRC hợp lệ |
| Cài bản cập nhật VSIX 1.1.2 | `code.cmd --install-extension ... --force`, sau đó `--list-extensions --show-versions` | **PASS** — xác nhận `group4-ictu.spotai-review@1.1.2` đã cài thành công |
| Web API trực tiếp | Uvicorn trên `http://127.0.0.1:8765` | **PASS** — `/api/health` HTTP 200 |
| Web API từ executable đóng gói | Chạy `spotai_backend.exe --web` với thư mục lưu trữ và workspace cấu hình như VS Code | **PASS** — health, snippet Python (0 vấn đề), repository Python (1 tệp, Quality Gate PASS), dashboard HTTP 200 và báo cáo trong thư mục lưu trữ riêng |
| Microsoft Edge thực | CDP smoke test `.vscode-test/browser_check.py` | **PASS** — kiểm tra giao diện 390/600/768/1200 px và các luồng phân tích |
| Cài đặt VSIX 1.1.1 qua VS Code CLI | `code.cmd --install-extension` vào cả thư mục kiểm thử cô lập và profile VS Code mặc định | **PASS** — `code.cmd --list-extensions --show-versions` trả `group4-ictu.spotai-review@1.1.1` |
| VS Code Extension Host cho VSIX 1.1.1 | Chạy host test trong VS Code 1.147.0 với `--extensionDevelopmentPath` trỏ trực tiếp tới thư mục VSIX đã cài và `--extensionTestsPath` | **PASS** — kích hoạt extension, đăng ký bốn lệnh, mở Dashboard, tự chạy backend, gọi API phân tích snippet/toàn bộ tệp Python và tệp Java qua HTTP 200; Java trả về 6 vấn đề |

Trình thông dịch Python 3.11.9 cài sẵn ở `C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe` đã có `fastapi`, `httpx`, `python-multipart` và `uvicorn`. Bộ kiểm thử Web/API đã chạy cùng toàn bộ 52 bài trên môi trường này vào ngày 20/11/2026. Các lệnh cần truy cập loopback hoặc VS Code được chạy với quyền sandbox phù hợp để khắc phục lỗi `EPERM` trước đó.

### Nghiệm thu Web trên trình duyệt Edge

- Kiểm tra ba tab Repository Reviewer, Live Code Playground và Architecture & Metrics ở độ rộng **390, 600, 768, 1200 px**. Không có phần tử tràn ngang ngoài viewport.
- Phân tích snippet Python sạch hiển thị **0 vấn đề**. Snippet có lỗi cú pháp hiển thị thông báo `SyntaxError` và ẩn kết quả cũ.
- Phân tích repository `repo3_clean_python` trả về Quality Gate **PASSED**. Link JSON, SARIF và dashboard HTML đều trả HTTP **200**.
- URL Git không hợp lệ trả thông báo rõ ràng và ẩn báo cáo cũ.
- Phân tích `repo1_ecommerce_java` trả Quality Gate **FAILED** và danh sách **9 vấn đề** tại lần chạy trên trình duyệt. Lọc theo mức độ, tìm kiếm và mở/đóng chi tiết vấn đề hoạt động.
- Upload tệp `.py` qua giao diện trả về **1 tệp** được phân tích thành công.

### Nghiệm thu VS Code Extension Host

Ngày 20/11/2026, gói **`vscode-extension/spotai-review-1.1.1.vsix`** đã cài thành công trong thư mục extension cô lập dưới `.vscode-test/vsix-1.1.1-install-extensions/` và trong profile VS Code mặc định. VS Code CLI nhận đúng `group4-ictu.spotai-review@1.1.1`. Backend `.exe` trong gói đã tự khởi chạy từ extension cài đặt, sử dụng cổng `127.0.0.1` ngẫu nhiên.

Kiểm thử mock của extension xác nhận bốn lệnh `spotai.openDashboard`, `spotai.reviewSelection`, `spotai.reviewCurrentFile`, `spotai.startServer`, cách nhận mã nguồn đang chọn/tệp đang mở, khởi chạy backend tự động từ thư mục cài extension, thư mục lưu trữ riêng, workspace path, và nội dung CSP.

**Extension Host thật cho bản 1.1.1 đã PASS trên VS Code 1.147.0.** Kết quả tại `.vscode-test/extension-host-result.json` xác nhận extension được nạp trực tiếp từ thư mục cài VSIX, bốn lệnh SpotAI đăng ký thành công, Dashboard và panel **SpotAI Code Review** mở được. Log `SpotAI Backend` xác nhận cả ba thao tác phân tích có HTTP `POST /api/analyze-snippet` trả mã 200, gồm snippet Python (0 vấn đề), tệp Python đầy đủ (0 vấn đề) và `OrderProcessor.java` (6 vấn đề). Kết quả HTML cho vấn đề, metrics, Quality Gate và nút nhảy dòng đã được kiểm tra bằng bộ unit test của extension. Chưa quan sát trực quan mọi chi tiết hiển thị bên trong Webview ở phiên người dùng thông thường.

**Bản 1.1.2 đã được xây dựng và cài đặt thành công trên VS Code.** Kiểm thử mock extension và 52 bài Python tiếp tục PASS sau khi cập nhật. Kiểm thử Extension Host thực nêu trên được thực hiện với bản 1.1.1. Chưa chạy lại toàn bộ kịch bản Extension Host thật trên bản 1.1.2.

**Lưu trữ sau kiểm thử:** Sau khi ghi nhận kết quả, các log, ảnh chụp và profile thử nghiệm trong `.vscode-test/`, các bản VSIX cũ và báo cáo thử dư thừa đã được xóa để giảm dung lượng. Báo cáo này lưu lại kết quả đã quan sát. Mã kiểm thử tự động chính vẫn nằm trong `tests/` và `vscode-extension/test/`. Bản cài được giữ và phát hành kèm mã nguồn là `spotai-review-1.1.2.vsix`.

**Phạm vi còn cần kiểm tra trong buổi demo:** quan sát trực quan nội dung iframe của Dashboard và chi tiết kết quả phân tích được render từ editor. Kịch bản clone URL GitHub thực chưa được thử với mạng Internet bên ngoài. Đề xuất AI từ dịch vụ cloud phụ thuộc API key và kết nối tại thời điểm demo.

## 2. Benchmark thực đo trên repository mẫu

Lệnh chạy `python evaluate_benchmarks.py` đo thời gian phân tích bằng `time.perf_counter` trên **một lần chạy cục bộ**, ngày 16/11/2026. Số liệu nằm trong `reports/evaluation_benchmark.json` và có thể thay đổi giữa các lần chạy.

| Repository | Tệp | LOC | Vấn đề | CC tối đa | Quality Gate | Thời gian |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| `repo1_ecommerce_java` | 2 | 109 | 10 | 14 | **FAIL** | 0,0386 s |
| `repo2_payment_gateway` | 2 | 108 | 9 | 10 | **FAIL** | 0,0275 s |
| `repo3_clean_python` | 1 | 9 | 0 | 2 | **PASS** | 0,0137 s |

Với hai repository đầu, adapter đã đọc được SpotBugs XML mẫu có sẵn. Với repository Python sạch, SpotBugs có trạng thái `not_available`.

Các chỉ số **precision, recall, F1, CC sau refactoring AI** chưa được đo, được ghi `null` trong JSON. Để tính chúng cần dữ liệu đối chứng gán nhãn độc lập hoặc áp dụng và phân tích lại mã nguồn sau khi sửa. Phân tích Java hiện dựa trên heuristic/regex nên các phát hiện và CC cần được đối chiếu thủ công khi báo cáo học phần.

## 3. Báo cáo và luồng demo

Các báo cáo đã sinh:

- `reports/repo1_ecommerce_java/analysis_report.json`, `analysis_report.sarif`, `dashboard.html`.
- `reports/repo2_payment_gateway/analysis_report.json`, `analysis_report.sarif`, `dashboard.html`.
- `reports/repo3_clean_python/analysis_report.json`, `analysis_report.sarif`, `dashboard.html`.

Luồng trình diễn được chuẩn bị trong `README.md`, bắt đầu từ CLI, tiếp tục Web trên `127.0.0.1`, sau đó VS Code Extension. Hai repository đầu minh họa Quality Gate FAIL. Repository Python sạch minh họa Quality Gate PASS.

**Tình trạng nghiệm thu:** 52/52 bài kiểm thử Python ở lần chạy trước, quy trình HTTP Web/Edge, kiểm thử extension bằng mock, backend `.exe` thực, đóng gói VSIX 1.1.1, cài đặt vào VS Code mặc định và chạy Extension Host thật trên VS Code 1.147.0 đều **PASS**. Các lệnh phân tích Python/Java đã gọi backend và nhận kết quả. Phần hiển thị chi tiết trong iframe và panel vẫn cần được quan sát trực quan khi demo.
