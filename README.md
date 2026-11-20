# SpotAI-Review

**Đồ án học phần Công nghệ phần mềm — ICTU**<br>
**Giảng viên:** TS. Nguyễn Thanh Hải<br>
**Thành viên:** Dương Lê Thưởng, Dương Quốc Toản, Nguyễn Thành Trung

SpotAI-Review phân tích tĩnh mã nguồn **Python và Java** qua cùng một pipeline, phát hiện code smell, tính cyclomatic complexity (CC), tìm đoạn code trùng lặp, đọc báo cáo SpotBugs XML và đề xuất hướng refactoring. Có ba cách sử dụng là **CLI**, **Web HTML** và **VS Code Extension**. Phân tích tĩnh hoạt động khi chưa có API key AI.

## 1. Cài đặt trên Windows

Cần Python 3.10 trở lên, Git (khi phân tích repository từ xa), Node.js/npm (khi đóng gói extension) và VS Code (khi sử dụng extension).

Mở PowerShell tại thư mục dự án:

```powershell
cd D:\spotai_review
python -m pip install -r requirements.txt
```

Nếu muốn dùng virtual environment, tạo và kích hoạt môi trường riêng trước khi cài dependencies. Phần CLI phân tích tĩnh sử dụng thư viện chuẩn Python. FastAPI, uvicorn và python-multipart cần thiết cho Web. Các thư viện phát triển khác được khai báo trong `requirements.txt`.

## 2. CLI / Terminal

```powershell
# Phân tích repository Java, tạo JSON, SARIF, HTML và Markdown
python spotai_cli.py --repo sample_repos/repo1_ecommerce_java --milestone 4 --output-dir reports/demo_java

# Phân tích repository có Python và Java
python spotai_cli.py --repo sample_repos/repo2_payment_gateway --output-dir reports/demo_mixed

# Thay đổi ngưỡng kiểm tra
python spotai_cli.py --repo sample_repos/repo2_payment_gateway --clone-threshold 0.85 --min-clone-lines 7 --max-cc 10 --milestone 4

# Trả exit code 2 khi Quality Gate thất bại
python spotai_cli.py --repo sample_repos/repo1_ecommerce_java --fail-on-gate

# Phân tích Git repository qua HTTPS khi có Internet và Git
python spotai_cli.py --repo https://github.com/owner/repository.git
```

Mỗi lần chạy sinh `analysis_report.json`, `analysis_report.sarif`, `dashboard.html`, `pr_comment.md` trong `--output-dir`. Mở trực tiếp `dashboard.html` bằng trình duyệt. Mã thoát `0` là hoàn tất phân tích, `1` là tham số/thao tác thất bại, `2` là Quality Gate không đạt khi có `--fail-on-gate` (hoặc đối với tham số CLI bị `argparse` từ chối). Nếu không dùng `--fail-on-gate`, CLI vẫn tạo báo cáo khi Gate FAIL.

## 3. Web HTML / FastAPI

```powershell
python spotai_cli.py --web --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`, tài liệu API tại `http://127.0.0.1:8000/docs`. Giao diện hỗ trợ tải `.py`, `.java`, `.zip`, nhập đường dẫn repository cục bộ hoặc GitHub HTTPS URL, và dán snippet vào Playground. Sau khi phân tích repository, chọn dashboard HTML hoặc tải báo cáo JSON/SARIF.

Các endpoint chính:

| Endpoint | Chức năng |
| --- | --- |
| `GET /api/health` | Kiểm tra backend và nhà cung cấp AI |
| `POST /api/analyze-repo` | Phân tích repository, trả số liệu và đường dẫn dashboard |
| `POST /api/upload-and-analyze` | Tải tệp/ZIP và phân tích |
| `POST /api/analyze-snippet` | Phân tích snippet Python/Java |
| `GET /dashboard/{id}` | Mở dashboard HTML |
| `GET /reports/{id}/{json\|sarif\|html}` | Tải báo cáo |

**Giới hạn mặc định cho demo cục bộ**

- API Web chỉ chấp nhận URL `https://github.com/owner/repository` hoặc `.git`, giới hạn clone 45 giây.
- Đường dẫn repository trên Web được giới hạn trong thư mục SpotAI-Review. Muốn phân tích dự án ở nơi khác, cấu hình biến môi trường PowerShell trước khi chạy server:

  ```powershell
  $env:SPOTAI_ALLOWED_ROOTS = 'D:\MyPythonProject;E:\School\JavaProject'
  python spotai_cli.py --web
  ```

- Chỉ cho phép CORS origin được cấu hình chủ động qua `SPOTAI_CORS_ORIGINS`. Giao diện Web dùng cùng origin nên không cần khai báo.
- Tổng dữ liệu upload tối đa **20 MB**, nội dung ZIP sau giải nén tối đa **100 MB**, ZIP tối đa **1.000 mục**. Các đường dẫn vượt phạm vi và symlink ZIP bị từ chối.
- Snippet gửi API tối đa **1 MB**. Tệp sai định dạng hoặc repository không có Python/Java được thông báo trong giao diện.

## 4. VS Code Extension

Có thể mở một dự án Python/Java bất kỳ trong VS Code để review ngay trong editor. Extension **1.1.2 cho Windows x64** chứa sẵn backend và tự khởi chạy khi mở dashboard hoặc phân tích code.

Cài đặt `vscode-extension/spotai-review-1.1.2.vsix` qua **Extensions: Install from VSIX...** hoặc bằng lệnh:

```powershell
code --install-extension vscode-extension\spotai-review-1.1.2.vsix
```

Mặc định không cần khai báo cấu hình. Nếu muốn kết nối một server Web có sẵn, người dùng có thể tùy chọn `spotai.serverUrl` trong Settings.

Bốn lệnh sử dụng:

1. **SpotAI: Open Review Dashboard** — mở Web trong panel.
2. **SpotAI: Review Selected Snippet** — phân tích vùng code đang chọn và hiển thị kết quả trong panel **SpotAI Code Review**.
3. **SpotAI: Analyze Entire Current File** — phân tích tệp Python/Java đang mở, hiển thị tổng quan, findings, metrics, đề xuất AI và nút nhảy đến dòng mã nguồn.
4. **SpotAI: Start Local Web Server** — chủ động mở backend tích hợp.

Extension tự cấp cổng localhost và lưu báo cáo trong thư mục dữ liệu của VS Code. Máy nhận VSIX không cần cài Python hoặc chạy server thủ công. Đóng gói và kiểm thử extension từ mã nguồn bằng:

```powershell
cd vscode-extension
npm test
npm run package
```

`npm run package` cần PyInstaller trên máy phát triển để build backend thành `.exe`, sau đó chạy `scripts/build_vsix.py` để tạo gói `.vsix` hoàn chỉnh. Chi tiết tại [vscode-extension/README.md](vscode-extension/README.md).

## 5. Dữ liệu mẫu, báo cáo và kiểm thử

- `sample_repos/repo1_ecommerce_java` là ví dụ Java có vấn đề để demo Quality Gate **FAIL**.
- `sample_repos/repo2_payment_gateway` chứa Python/Java có vấn đề để đối chiếu CLI, Web và VS Code.
- `sample_repos/repo3_clean_python` có Python đơn giản để demo Quality Gate **PASS**.

```powershell
# Tạo lại báo cáo JSON, SARIF, HTML và benchmark đo trực tiếp trên cả ba repository mẫu
python evaluate_benchmarks.py

# Chạy unit, API và security tests (sau khi cài dependencies)
python -m unittest discover -s tests -p 'test_*.py' -v

# Kiểm thử extension
cd vscode-extension
npm test
```

Báo cáo mẫu được ghi tại `reports/repo1_ecommerce_java/`, `reports/repo2_payment_gateway/`, `reports/repo3_clean_python/` và thống kê benchmark tại `reports/evaluation_benchmark.json`. Các tệp trong `reports/` cùng `.vsix` có thể bị Git bỏ qua và được tạo lại bằng lệnh trên. Kết quả kiểm thử đã xác minh cùng giới hạn môi trường ở [TEST_RESULTS.md](TEST_RESULTS.md).

## 6. Phạm vi kỹ thuật cần trình bày trong buổi nghiệm thu

- Python được phân tích bằng `ast` chuẩn. Bộ phân tích Java hiện tại dùng quy tắc cấu trúc/regex để ước lượng method, complexity và code smell, nên kết quả Java cần hiểu theo mức **phân tích heuristic**.
- SpotBugs adapter đọc XML do SpotBugs tạo sẵn (ví dụ `spotbugsXml.xml`). Khi không tìm thấy XML, trạng thái hiển thị `not_available`. Việc tạo bytecode và chạy SpotBugs binary cần thao tác riêng.
- Chỉ số CC, LOC, MI và số lượng phát hiện phản ánh dữ liệu phân tích hiện tại. **Precision, recall, F1 và CC sau refactoring chưa được đo** nếu chưa có dữ liệu gán nhãn và code sau sửa được kiểm tra lại.
- Đề xuất AI ghi tên nhà cung cấp. Khi chưa có API key hoặc dịch vụ lỗi, hệ thống sử dụng gợi ý rule-based được đánh dấu là offline. Các gợi ý phải được kiểm tra trước khi áp dụng.
- Quality Gate chỉ PASS khi đã quét ít nhất một file, không có lỗi phân tích, không có lỗi mức HIGH/CRITICAL và CC tối đa không vượt ngưỡng.

**Luồng demo** — phân tích `repo2_payment_gateway` trên CLI, mở cùng đường dẫn trên Web, rồi mở một tệp Java/Python của mẫu này trong VS Code để review. Chạy thêm `repo3_clean_python` để minh họa Gate PASS.
