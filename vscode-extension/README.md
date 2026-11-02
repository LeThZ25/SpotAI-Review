# SpotAI-Review VS Code Extension

VS Code Extension for **SpotAI-Review** (Topic 4 — Software Engineering, Group 4: Dương Lê Thưởng & Dương Quốc Toản).

This extension provides an interactive, side-by-side code review experience right inside Visual Studio Code, combining static analysis (SpotBugs + AST Smells + McCabe/Cognitive Complexity) with LLM-powered refactoring suggestions for **Java** and **Python**.

---

## 🌟 Key Features

1. **Side-by-Side Review Dashboard (`spotai.openDashboard`)**:
   - Opens the unified SpotAI Review Webview directly in VS Code (`ViewColumn.Beside`).
   - Switch between **Repository Reviewer**, **Live Code Playground**, and **Architecture Specs**.
2. **Instant Snippet Review (`spotai.reviewSelection`)**:
   - Highlight any Java method or Python function in your editor.
   - Right-click and choose **"SpotAI: Review Selected Snippet"**.
   - Instantly calculates McCabe CC, Cognitive Complexity, Maintainability Index, detects code smells, and presents Before/After refactoring.
3. **Analyze Entire Active File (`spotai.reviewCurrentFile`)**:
   - Review the complete active `.java` or `.py` file in one click.
4. **Dual Architecture (Webview Bridge)**:
   - Connects seamlessly to a local FastAPI backend (`http://localhost:8000`) or cloud-deployed instance (e.g., Render/Railway).
   - If the backend is not running, the extension offers a 1-click button to launch `python spotai_cli.py --web` inside the VS Code integrated terminal.

---

## 🚀 Getting Started

### Prerequisites
- VS Code `^1.75.0`
- Python 3.10+ with `fastapi`, `uvicorn`, and `python-docx` installed:
  ```bash
  pip install -r requirements.txt
  ```

### Running & Debugging in VS Code
1. Open the project folder `d:\spotai_review\vscode-extension` in VS Code.
2. Press `F5` (or click **Run and Debug** -> **Run Extension**).
3. A new **Extension Development Host** window will open.
4. In the new window:
   - Open any Java (`.java`) or Python (`.py`) file.
   - Highlight a block of code, right click, and select **"SpotAI: Review Selected Snippet"**.
   - Or press `Ctrl+Shift+P` and type `SpotAI: Open Review Dashboard`.

---

## 📦 Packaging to `.vsix`

To bundle the extension into a single `.vsix` installer for distribution:

1. Install `@vscode/vsce`:
   ```bash
   npm install -g @vscode/vsce
   ```
2. Navigate to `vscode-extension`:
   ```bash
   cd vscode-extension
   ```
3. Run package command:
   ```bash
   vsce package
   ```
4. Install the generated `.vsix` in VS Code via:
   - Command Palette: `Extensions: Install from VSIX...`
   - Or command line: `code --install-extension spotai-review-1.0.0.vsix`

---

## ⚙️ Extension Settings

This extension contributes the following settings:

* `spotai.serverUrl`: The URL of the SpotAI review backend (default: `http://127.0.0.1:8000`). Change this to your deployed cloud URL (e.g. `https://spotai-review.onrender.com`) to run completely serverless on your machine.
* `spotai.pythonPath`: Python executable to run when auto-starting the local backend (default: `python`).

---

## 👥 Authors
- **Group 4 - Software Engineering (ICTU)**:
  - Dương Lê Thưởng
  - Dương Quốc Toản

