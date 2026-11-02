# SpotAI-Review: Static Code Analysis & AI Code Review Tool

**Course:** Software Engineering — **Group 4**  
**Instructor:** Dr. Nguyen Thanh Hai  
**Team Members:**
- **Duong Le Thuong** (`DTC235340030`) — Core Static Analysis Engine, SpotBugs Bytecode XML Adapter, AST Metrics & Code Smell Rules, Web Application & Live Code Playground
- **Duong Quoc Toan** (`DTC235210055`) — Configurable Token/AST Clone Detector, LLM Refactoring Engine, GitHub Actions CI/CD Bot, VS Code Extension & SARIF/HTML Dashboard

---

## 1. Overview & Architecture
`SpotAI-Review` is a hybrid static code analysis and automated pull request review ecosystem that integrates:
- **SpotBugs Bytecode Bug Detection**: XML/SARIF parser for standard Java security, null-pointer, and resource leak vulnerabilities.
- **AST Metrics & Multi-Smell Detection**: McCabe Cyclomatic Complexity, Halstead Volume, Maintainability Index (MI), Long Method, God Class, Deeply Nested Control Flow, Feature Envy, Long Parameter List, and Magic Numbers for Java and Python.
- **Configurable Clone Detector**: Sliding token-window similarity detector identifying Type-1 (identical), Type-2 (renamed identifiers), and Type-3 (modified statements) code clones.
- **LLM-Powered Refactoring Engine**: Groq (Llama-3.3-70b-versatile) & Google Gemini integrations with local heuristic fallback for instantaneous Before/After code patches.
- **Dual Client Ecosystem**: Modern FastAPI Single-Page Web Dashboard + VS Code Extension via Webview Bridge architecture.
- **Remote Git & Shallow Clones**: Direct analysis of GitHub repositories via `git clone --depth 1`.

---

## 2. Quick Start (CLI)

```bash
# Install dependencies
pip install -r requirements.txt

# Run Milestone 1 (SpotBugs XML + AST Code Smells & Cyclomatic Complexity)
python spotai_cli.py --repo sample_repos/repo1_ecommerce_java --milestone 1

# Run Milestone 4 (Full Hybrid Pipeline: SpotBugs + AST + Clones + AI Refactoring)
python spotai_cli.py --repo sample_repos/repo1_ecommerce_java --output-dir reports/repo1 --milestone 4

# Run on Remote GitHub Repository (Shallow Clone)
python spotai_cli.py --repo https://github.com/bottlepy/bottle --output-dir reports/bottle_repo

# Run Benchmark Evaluation on Sample Repositories
python evaluate_benchmarks.py

# Run Full Test Suite (20/20 unit tests)
python -m unittest discover tests
```

---

## 3. Web Dashboard & Live Code Playground

Launch the interactive single-page web application:
```bash
python spotai_cli.py --web --port 8000
```
Open your browser at **`http://localhost:8000`** to access:
1. **Repository Reviewer**: Analyze any local folder or paste a public GitHub URL. Checks automatically for Java/Python files and provides friendly warnings if unsupported files are submitted.
2. **Live Code Playground**: Test code snippets in real-time. Input any standalone Java method or Python function to see:
   - McCabe Cyclomatic Complexity & Maintainability Index (MI / 100).
   - Structural code smell detection.
   - Real-time Before/After AI refactoring diff.
   - Quick test samples for SQL injection, deeply nested loops, and clean code.
3. **Architecture & Engine Specs**: Detailed visual breakdown of the multi-engine pipeline.
4. **Interactive REST API**: Full OpenAPI / Swagger documentation at `http://localhost:8000/docs`.

---

## 4. Visual Studio Code Extension

Located in `vscode-extension/`:
- **Side-by-side Review**: Run code quality inspections alongside your source code.
- **Right-click Snippet Review**: Highlight any Java or Python code, right-click, and select `"SpotAI: Review Selected Snippet"`.
- **Integrated Terminal Launcher**: Auto-detects if the backend server is running and provides a 1-click launcher.
- See [`vscode-extension/README.md`](vscode-extension/README.md) for debug and `.vsix` packaging instructions.

---

## 5. Cloud Deployment (Render.com / Railway)

The web dashboard is ready for one-click deployment:
- Blueprint file: `render.yaml`
- Web process definition: `Procfile`
- Python runtime dependencies: `requirements.txt`

To deploy on Render:
1. Push your repository to GitHub.
2. In Render dashboard, click **New** -> **Blueprint** and select your repository.
3. Render automatically provisions the Python Web Service running `uvicorn src.spotai.web_server:app`.

---

## 6. Project Deliverables & Reports
- **Formal Progress Report**: `Group4_Progress_Report_SpotAI_Review.docx` (Strictly formatted to ICTU standard: A4, 3.5-2.0-2.5-2.5cm margins, Times New Roman 13pt, 1.3 line spacing).
- **Master Technical Architecture Report**: `artifacts/spotai_review_master_technical_report.md`.
- **Benchmark Evaluation Report**: `BENCHMARK_REPORT.md` (Precision, Recall, F1 on synthetic and real test suites).
