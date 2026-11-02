"""
Web Server & REST API for SpotAI-Review
Provides high-performance REST APIs and Unified Web UI for:
1. Repository Review (Drag & Drop files/ZIP, Local directory, or remote GitHub URL with Shallow Clone)
2. Live Code Playground (Instant snippet analysis and AI refactoring for Java & Python)
3. Interactive HTML Dashboard & Diagnostics
Serves both standalone browser access and VS Code Extension Webview.
"""
import os
import sys
import shutil
import zipfile
import uuid
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure src path is available
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from spotai.pipeline import SpotAIPipeline
from spotai.repo_resolver import RepoResolver, RepoResolverError
from spotai.snippet_analyzer import SnippetAnalyzer
from spotai.reporter import ReportExporter
from spotai.ai_refactor import AIRefactoringEngine

app = FastAPI(
    title="SpotAI-Review Engine API",
    description="REST API for Static Code Analysis & AI Code Review (SpotBugs + AST + Clone + LLM)",
    version="1.0.0"
)

# Enable CORS for VS Code Webview and cross-origin tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

snippet_analyzer = SnippetAnalyzer()


class AnalyzeRepoRequest(BaseModel):
    repo: str
    milestone: int = 4
    clone_threshold: float = 0.80
    min_clone_lines: int = 7
    max_cc: int = 10
    cleanup_temp: bool = True


class AnalyzeSnippetRequest(BaseModel):
    code: str
    language: str  # "java" or "python"


@app.get("/api/health")
def health_check():
    ai_engine = AIRefactoringEngine()
    return {
        "status": "healthy",
        "version": "1.0.0",
        "active_ai_provider": ai_engine.active_provider_label,
        "supported_languages": ["java", "python"],
        "engines": ["SpotBugs Bytecode", "AST Code Smells", "Clone Detector", "AI Refactoring Engine"]
    }


@app.post("/api/analyze-snippet")
def analyze_snippet(req: AnalyzeSnippetRequest):
    """Real-time analysis of code snippets for the Live Code Playground."""
    result = snippet_analyzer.analyze_snippet(req.code, req.language)
    return result


@app.post("/api/analyze-repo")
def analyze_repo(req: AnalyzeRepoRequest):
    """
    Analyzes local directory or clones remote GitHub repository with shallow clone.
    Validates presence of Java and Python files with user-friendly warnings.
    """
    repo_input = req.repo.strip()
    if not repo_input:
        raise HTTPException(status_code=400, detail="Repository path or URL cannot be empty.")

    resolver = RepoResolver()
    try:
        repo_dir, is_temp, repo_name = resolver.resolve(repo_input)
    except RepoResolverError as err:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(err)}
        )

    # Pre-scan verification for Java and Python files
    java_files = []
    py_files = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "temp_repos", "node_modules", "target", "build", ".venv"}]
        for f in files:
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))
            elif f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    total_supported_files = len(java_files) + len(py_files)
    if total_supported_files == 0:
        if is_temp and req.cleanup_temp:
            resolver.cleanup(repo_dir)
        return {
            "status": "no_supported_files",
            "message": (
                f"No Java (*.java) or Python (*.py) source files were found in '{repo_name}'. "
                "SpotAI-Review specializes in Java and Python. Please verify repository contents."
            ),
            "repository_name": repo_name,
            "files_scanned": 0,
            "report": None
        }

    try:
        pipeline = SpotAIPipeline(
            clone_threshold=req.clone_threshold,
            min_clone_lines=req.min_clone_lines,
            max_cc=req.max_cc,
            milestone=req.milestone,
        )
        report = pipeline.analyze(repo_dir, repo_name=repo_name)

        out_dir = os.path.abspath(os.path.join("reports", "web_reports", repo_name))
        os.makedirs(out_dir, exist_ok=True)

        ReportExporter.save_json(report, os.path.join(out_dir, "analysis_report.json"))
        ReportExporter.save_sarif(report, os.path.join(out_dir, "analysis_report.sarif"))
        ReportExporter.save_html_dashboard(report, os.path.join(out_dir, "dashboard.html"))

        return {
            "status": "success",
            "repository_name": repo_name,
            "is_temporary": is_temp,
            "detected_files": {
                "java": len(java_files),
                "python": len(py_files),
                "total": total_supported_files
            },
            "report": report.to_dict(),
            "dashboard_url": f"/dashboard/{repo_name}"
        }

    finally:
        if is_temp and req.cleanup_temp:
            resolver.cleanup(repo_dir)


@app.post("/api/upload-and-analyze")
async def upload_and_analyze(
    files: List[UploadFile] = File(...),
    milestone: int = Form(4),
    clone_threshold: float = Form(0.80),
    min_clone_lines: int = Form(7),
    max_cc: int = Form(10),
):
    """
    Accepts direct upload or drag & drop of .java, .py, or .zip files.
    Extracts archives, saves files into a temporary isolated workspace, and runs the analysis.
    """
    upload_id = f"upload_{uuid.uuid4().hex[:8]}"
    temp_dir = os.path.abspath(os.path.join("temp_repos", upload_id))
    os.makedirs(temp_dir, exist_ok=True)

    try:
        for file in files:
            filename = file.filename or "unknown"
            lower_name = filename.lower()
            
            if lower_name.endswith(".zip"):
                zip_path = os.path.join(temp_dir, filename)
                with open(zip_path, "wb") as f:
                    content = await file.read()
                    f.write(content)
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_dir)
                try:
                    os.remove(zip_path)
                except Exception:
                    pass
            elif lower_name.endswith(".java") or lower_name.endswith(".py"):
                # Save single source file
                clean_name = os.path.basename(filename)
                file_dest = os.path.join(temp_dir, clean_name)
                with open(file_dest, "wb") as f:
                    content = await file.read()
                    f.write(content)
            else:
                # Store other files in case needed
                clean_name = os.path.basename(filename)
                file_dest = os.path.join(temp_dir, clean_name)
                with open(file_dest, "wb") as f:
                    content = await file.read()
                    f.write(content)

        # Scan for Java and Python files
        java_files = []
        py_files = []
        for root, dirs, f_list in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", "target", "build", ".venv"}]
            for f in f_list:
                if f.endswith(".java"):
                    java_files.append(os.path.join(root, f))
                elif f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        total_supported = len(java_files) + len(py_files)
        if total_supported == 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                "status": "no_supported_files",
                "message": (
                    "No Java (*.java) or Python (*.py) source files were found in the uploaded file(s). "
                    "SpotAI-Review specializes in Java and Python. Please upload .java, .py, or a .zip archive containing them."
                ),
                "repository_name": upload_id,
                "files_scanned": 0,
                "report": None
            }

        pipeline = SpotAIPipeline(
            clone_threshold=clone_threshold,
            min_clone_lines=min_clone_lines,
            max_cc=max_cc,
            milestone=milestone,
        )
        report = pipeline.analyze(temp_dir, repo_name=upload_id)

        out_dir = os.path.abspath(os.path.join("reports", "web_reports", upload_id))
        os.makedirs(out_dir, exist_ok=True)

        ReportExporter.save_json(report, os.path.join(out_dir, "analysis_report.json"))
        ReportExporter.save_sarif(report, os.path.join(out_dir, "analysis_report.sarif"))
        ReportExporter.save_html_dashboard(report, os.path.join(out_dir, "dashboard.html"))

        return {
            "status": "success",
            "repository_name": upload_id,
            "is_temporary": True,
            "detected_files": {
                "java": len(java_files),
                "python": len(py_files),
                "total": total_supported
            },
            "report": report.to_dict(),
            "dashboard_url": f"/dashboard/{upload_id}"
        }

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/dashboard/{repo_name}", response_class=HTMLResponse)
def get_dashboard(repo_name: str):
    """Serves the generated interactive HTML dashboard for a specific repository."""
    dashboard_path = os.path.abspath(os.path.join("reports", "web_reports", repo_name, "dashboard.html"))
    if not os.path.exists(dashboard_path):
        # Fallback to local demo if exists
        alt_path = os.path.abspath(os.path.join("reports", repo_name, "dashboard.html"))
        if os.path.exists(alt_path):
            dashboard_path = alt_path
        else:
            raise HTTPException(status_code=404, detail=f"Dashboard for repository '{repo_name}' not found.")

    with open(dashboard_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/", response_class=HTMLResponse)
def serve_index():
    """Serves the Unified SpotAI-Review Web Application (Repository Review + Live Playground)."""
    return get_unified_html()


def get_unified_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SpotAI-Review • Code Quality & AI Review Platform</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --accent: #38bdf8;
      --accent-hover: #0284c7;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --code-bg: #030712;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
    body { background-color: var(--bg); color: var(--text); line-height: 1.5; min-height: 100vh; display: flex; flex-direction: column; }
    header { background: #0f172a; border-bottom: 1px solid var(--card-border); padding: 14px 28px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-logo { width: 36px; height: 36px; background: linear-gradient(135deg, #38bdf8, #6366f1); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 1.2rem; color: #fff; }
    .brand-text h1 { font-size: 1.15rem; font-weight: 700; color: #fff; }
    .brand-text p { font-size: 0.75rem; color: var(--text-muted); }
    .nav-tabs { display: flex; gap: 8px; background: #1e293b; padding: 4px; border-radius: 8px; }
    .nav-tab { background: transparent; border: none; color: var(--text-muted); padding: 8px 16px; border-radius: 6px; font-size: 0.88rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
    .nav-tab.active { background: #38bdf8; color: #0b0f19; }
    .container { max-width: 1200px; margin: 24px auto; padding: 0 20px; width: 100%; flex: 1; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
    .card-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 8px; color: #fff; display: flex; align-items: center; gap: 8px; }
    .card-desc { font-size: 0.88rem; color: var(--text-muted); margin-bottom: 18px; }
    
    /* Mode Pills */
    .mode-pills { display: flex; gap: 10px; margin-bottom: 16px; }
    .mode-btn { background: #1e293b; border: 1px solid var(--card-border); color: var(--text-muted); padding: 6px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
    .mode-btn.active-mode { background: rgba(56, 189, 248, 0.15); border-color: var(--accent); color: var(--accent); }
    
    /* Drag & Drop Zone */
    .drop-zone {
      border: 2px dashed rgba(56, 189, 248, 0.4);
      border-radius: 12px;
      padding: 30px 20px;
      text-align: center;
      background: rgba(15, 23, 42, 0.4);
      cursor: pointer;
      transition: all 0.2s ease;
      margin-bottom: 16px;
    }
    .drop-zone:hover, .drop-zone.dragover {
      border-color: var(--accent);
      background: rgba(56, 189, 248, 0.08);
      transform: translateY(-1px);
    }
    .drop-icon { font-size: 2.2rem; margin-bottom: 8px; }
    .drop-title { font-size: 1rem; font-weight: 600; color: #f1f5f9; margin-bottom: 4px; }
    .drop-subtitle { font-size: 0.82rem; color: var(--text-muted); }
    .file-list { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
    .file-chip {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 0.8rem;
      color: #38bdf8;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .file-chip-remove { cursor: pointer; color: var(--text-muted); font-weight: bold; }
    .file-chip-remove:hover { color: var(--danger); }

    .input-group { display: flex; gap: 10px; margin-bottom: 16px; }
    input[type="text"], select, textarea { background: #030712; border: 1px solid var(--card-border); color: var(--text); border-radius: 8px; padding: 10px 14px; font-size: 0.9rem; outline: none; transition: border-color 0.2s; }
    input[type="text"]:focus, select:focus, textarea:focus { border-color: var(--accent); }
    input[type="text"] { flex: 1; }
    .btn { background: #38bdf8; color: #0b0f19; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 0.9rem; display: inline-flex; align-items: center; gap: 8px; }
    .btn:hover:not(:disabled) { background: #0284c7; color: #fff; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-secondary { background: #1e293b; color: var(--text); border: 1px solid var(--card-border); }
    .btn-secondary:hover:not(:disabled) { background: #334155; }
    .grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .metric-card { background: #0f172a; border: 1px solid var(--card-border); border-radius: 10px; padding: 16px; border-left: 4px solid var(--accent); }
    .metric-card.good { border-left-color: var(--success); }
    .metric-card.danger { border-left-color: var(--danger); }
    .metric-label { font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; }
    .metric-val { font-size: 1.6rem; font-weight: 800; color: #fff; margin: 4px 0; }
    .metric-sub { font-size: 0.75rem; color: var(--text-muted); }
    .issue-item { background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
    .issue-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; background: rgba(255,255,255,0.02); }
    .issue-header:hover { background: rgba(255,255,255,0.05); }
    .badge { font-size: 0.72rem; padding: 2px 8px; border-radius: 4px; font-weight: 700; text-transform: uppercase; }
    .badge-high { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
    .badge-medium { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }
    .badge-low { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #0284c7; }
    .issue-body { padding: 16px; border-top: 1px solid var(--card-border); font-size: 0.88rem; background: #070b13; }
    .diff-block { background: var(--code-bg); padding: 14px; border-radius: 6px; font-family: "Consolas", monospace; font-size: 0.82rem; overflow-x: auto; margin-top: 10px; border: 1px solid #1f2937; }
    .limitations-alert { background: rgba(245, 158, 11, 0.1); border: 1px solid var(--warning); color: #fbbf24; padding: 10px; border-radius: 6px; font-size: 0.8rem; margin-top: 10px; }
    .playground-split { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 20px; }
    @media (max-width: 900px) { .playground-split { grid-template-columns: 1fr; } }
    .code-editor { width: 100%; height: 380px; font-family: "Consolas", monospace; font-size: 0.88rem; background: var(--code-bg); resize: vertical; line-height: 1.4; transition: border-color 0.2s; }
    .code-editor.dragover { border: 2px dashed var(--accent) !important; background: rgba(56, 189, 248, 0.05) !important; }
    .quick-samples { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    .badge-sample { background: #1e293b; border: 1px solid var(--card-border); color: var(--text-muted); padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; cursor: pointer; transition: all 0.2s; }
    .badge-sample:hover { background: #334155; color: var(--accent); }
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(0,0,0,0.3); border-radius: 50%; border-top-color: currentColor; animation: spin 0.8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .banner-alert { padding: 14px 18px; border-radius: 8px; margin-bottom: 18px; font-size: 0.88rem; background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #fca5a5; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-logo">S</div>
      <div class="brand-text">
        <h1>SpotAI-Review</h1>
        <p>Topic 4 • Group 4: Duong Le Thuong & Duong Quoc Toan</p>
      </div>
    </div>
    <div class="nav-tabs">
      <button class="nav-tab active" id="tab-btn-repo" onclick="switchTab('repo-tab')">📁 Repository Reviewer</button>
      <button class="nav-tab" id="tab-btn-playground" onclick="switchTab('playground-tab')">⚡ Live Code Playground</button>
      <button class="nav-tab" id="tab-btn-arch" onclick="switchTab('arch-tab')">🧠 Architecture & Metrics</button>
    </div>
  </header>

  <div class="container">
    <!-- TAB 1: REPOSITORY REVIEWER -->
    <div id="repo-tab" class="tab-content active">
      <div class="card">
        <div class="card-title">🔍 Scan & Review Repository</div>
        <div class="card-desc">Tải lên file mã nguồn trực tiếp bằng cách kéo thả, hoặc quét qua đường dẫn thư mục / GitHub URL.</div>
        
        <div class="mode-pills">
          <button id="mode-btn-upload" class="mode-btn active-mode" onclick="switchRepoMode('upload')">📂 Kéo thả File / Thư mục ZIP</button>
          <button id="mode-btn-url" class="mode-btn" onclick="switchRepoMode('url')">🔗 GitHub URL / Thư mục Local</button>
        </div>

        <div id="repo-alert-zone"></div>

        <!-- MODE 1: DRAG & DROP UPLOAD -->
        <div id="mode-upload-container">
          <div id="drop-zone" class="drop-zone" onclick="document.getElementById('file-upload-input').click()">
            <div class="drop-icon">📁</div>
            <div class="drop-title">Kéo & thả file <code>.java</code>, <code>.py</code> hoặc file <code>.zip</code> dự án vào đây</div>
            <div class="drop-subtitle">Hoặc <u>bấm vào đây để chọn file từ máy tính</u> (hỗ trợ chọn nhiều file cùng lúc)</div>
            <input type="file" id="file-upload-input" multiple accept=".java,.py,.zip" style="display:none;" onchange="handleFileSelect(event)" />
            <div id="file-chips" class="file-list"></div>
          </div>
          <div class="input-group" style="justify-content: flex-end; align-items:center;">
            <label style="font-size:0.85rem; color:var(--text-muted); margin-right:4px;">Chế độ Milestone:</label>
            <select id="upload-milestone" style="width: 180px;">
              <option value="4">Milestone 4 (Full Hybrid)</option>
              <option value="3">Milestone 3 (PR Bot)</option>
              <option value="2">Milestone 2 (AI + Clone)</option>
              <option value="1">Milestone 1 (SpotBugs + AST)</option>
            </select>
            <button class="btn" id="upload-btn" onclick="runUploadAnalysis()" disabled>
              <span id="upload-btn-text">Quét các File đã Tải lên</span>
            </button>
          </div>
        </div>

        <!-- MODE 2: URL / LOCAL PATH -->
        <div id="mode-url-container" style="display: none;">
          <div class="input-group">
            <input type="text" id="repo-input" placeholder="e.g. sample_repos/repo1_ecommerce_java hoặc https://github.com/bottlepy/bottle" value="sample_repos/repo1_ecommerce_java" />
            <select id="repo-milestone" style="width: 180px;">
              <option value="4">Milestone 4 (Full Hybrid)</option>
              <option value="3">Milestone 3 (PR Bot)</option>
              <option value="2">Milestone 2 (AI + Clone)</option>
              <option value="1">Milestone 1 (SpotBugs + AST)</option>
            </select>
            <button class="btn" id="repo-btn" onclick="runRepoAnalysis()">
              <span id="repo-btn-text">Run SpotAI Review</span>
            </button>
          </div>
        </div>
      </div>

      <div id="repo-results" style="display: none;">
        <div class="grid-4">
          <div class="metric-card" id="card-qg">
            <div class="metric-label">Quality Gate</div>
            <div class="metric-val" id="res-qg">-</div>
            <div class="metric-sub" id="res-qg-sub">Target: 0 High Issues & CC &le; 10</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Files & LOC</div>
            <div class="metric-val" id="res-files">-</div>
            <div class="metric-sub" id="res-loc">-</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Average / Max CC</div>
            <div class="metric-val" id="res-cc">-</div>
            <div class="metric-sub">McCabe Cyclomatic Complexity</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Maintainability Index</div>
            <div class="metric-val" id="res-mi">-</div>
            <div class="metric-sub">Target: &ge; 65.0 / 100.0</div>
          </div>
        </div>

        <div class="card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <div class="card-title" style="margin-bottom:0;">📋 Actionable Findings & AI Refactorings (<span id="res-issues-count">0</span>)</div>
            <a id="btn-full-dashboard" target="_blank" class="btn btn-secondary" style="font-size:0.82rem; padding: 6px 14px;">Open Full HTML Dashboard ↗</a>
          </div>
          <div id="repo-issues-list"></div>
        </div>
      </div>
    </div>

    <!-- TAB 2: LIVE CODE PLAYGROUND -->
    <div id="playground-tab" class="tab-content">
      <div class="card">
        <div class="card-title">⚡ Live Code Playground (Instant Review & Refactor)</div>
        <div class="card-desc">Nhập hoặc <strong>kéo thả trực tiếp file .java / .py vào khung soạn thảo bên dưới</strong>. SpotAI-Review tính toán McCabe CC, Cognitive Complexity, Maintainability Index và sinh bản vá Before/After real-time.</div>
        
        <div class="quick-samples">
          <span style="font-size:0.8rem; color:var(--text-muted); align-self:center;">Quick Test Samples:</span>
          <button class="badge-sample" onclick="loadSample('sql_java')">SQL Injection & Null Check (Java)</button>
          <button class="badge-sample" onclick="loadSample('nested_java')">Deeply Nested Loop & High CC (Java)</button>
          <button class="badge-sample" onclick="loadSample('param_py')">Long Parameter List (Python)</button>
          <button class="badge-sample" onclick="loadSample('clean_py')">Clean Code Example (Python)</button>
        </div>

        <div class="playground-split">
          <div class="editor-wrapper">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <label style="font-size:0.85rem; font-weight:600;">Input Source Code (Kéo thả file vào đây):</label>
              <select id="snippet-lang" style="padding: 4px 10px; font-size:0.82rem;" onchange="onLangChange()">
                <option value="java">Java (.java)</option>
                <option value="python">Python (.py)</option>
              </select>
            </div>
            <textarea id="snippet-code" class="code-editor" placeholder="// Paste your Java or Python method here, or drag & drop a .java / .py file..."></textarea>
            <div style="margin-top: 12px; display:flex; justify-content:flex-end;">
              <button class="btn" id="snippet-btn" onclick="runSnippetAnalysis()">
                <span id="snippet-btn-text">Analyze & Refactor Code</span>
              </button>
            </div>
          </div>

          <div>
            <div style="font-size:0.85rem; font-weight:600; margin-bottom:8px;">Real-Time Review Results:</div>
            <div id="snippet-results-placeholder" style="height: 380px; border: 1px dashed var(--card-border); border-radius: 10px; display: flex; align-items:center; justify-content:center; color:var(--text-muted); font-size:0.88rem; text-align:center; padding:20px;">
              Paste code on the left or drop a source file,<br/>then click "Analyze & Refactor Code" to see real-time metrics and AI refactoring.
            </div>
            <div id="snippet-results" style="display:none;">
              <div class="grid-4" style="grid-template-columns: repeat(2, 1fr); margin-bottom: 16px;">
                <div class="metric-card">
                  <div class="metric-label">Cyclomatic Complexity</div>
                  <div class="metric-val" id="snip-cc">-</div>
                  <div class="metric-sub">McCabe independent paths</div>
                </div>
                <div class="metric-card">
                  <div class="metric-label">Maintainability Index</div>
                  <div class="metric-val" id="snip-mi">-</div>
                  <div class="metric-sub">Score out of 100.0</div>
                </div>
              </div>

              <div class="card" style="padding: 16px; margin-bottom: 16px;">
                <div style="font-size: 0.88rem; font-weight: 700; margin-bottom: 8px;">Detected Smells / Defects (<span id="snip-issues-count">0</span>):</div>
                <div id="snip-issues-list"></div>
              </div>

              <div class="card" style="padding: 16px;">
                <div style="font-size: 0.88rem; font-weight: 700; margin-bottom: 8px;">🤖 AI Refactoring Patch:</div>
                <div id="snip-ai-explanation" style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 8px;"></div>
                <pre class="diff-block"><code id="snip-diff">-</code></pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: ARCHITECTURE & METRICS -->
    <div id="arch-tab" class="tab-content">
      <div class="card">
        <div class="card-title">🧠 SpotAI-Review Architecture & Engine Specifications</div>
        <div class="card-desc">Technical implementation summary for Software Engineering Topic 4 (Group 4).</div>
        
        <div class="grid-4" style="margin-top: 20px;">
          <div class="metric-card">
            <div class="metric-label">Engine 1</div>
            <div class="metric-val" style="font-size:1.2rem;">SpotBugs XML</div>
            <div class="metric-sub">Parses bytecode bug reports (NullPtr, SQLi, Resource Leaks) via native XML parser.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 2</div>
            <div class="metric-val" style="font-size:1.2rem;">AST Smells</div>
            <div class="metric-sub">Detects Long Method, God Class, Feature Envy, Long Parameters, Deep Nesting.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 3</div>
            <div class="metric-val" style="font-size:1.2rem;">Clone Detector</div>
            <div class="metric-sub">Sliding token-window similarity matching for Type-1, Type-2, and Type-3 clones.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 4</div>
            <div class="metric-val" style="font-size:1.2rem;">AI Refactoring</div>
            <div class="metric-sub">Groq (Llama-3.3-70b) & Gemini with deterministic local heuristic fallback.</div>
          </div>
        </div>

        <div class="card" style="margin-top: 16px; background: #070b13;">
          <div class="card-title" style="font-size: 0.95rem;">📊 Software Metric Formulas Implemented</div>
          <ul style="font-size: 0.86rem; color: var(--text-muted); margin-left: 20px; line-height: 1.8;">
            <li><strong>McCabe Cyclomatic Complexity:</strong> <code>CC = E - N + 2P</code> (calculated via AST decision node branches: if, while, for, and, or).</li>
            <li><strong>Cognitive Complexity:</strong> Evaluates mental burden based on nesting level depth increments.</li>
            <li><strong>Halstead Volume:</strong> <code>V = (N1 + N2) * log2(n1 + n2)</code> from distinct & total operators and operands.</li>
            <li><strong>Maintainability Index:</strong> <code>MI = max(0, (171 - 5.2*ln(V) - 0.23*CC - 16.2*ln(LOC)) * 100 / 171)</code>. Target &ge; 65.0.</li>
          </ul>
        </div>
      </div>
    </div>
  </div>

  <script>
    // Tab switching
    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
      const target = document.getElementById(tabId);
      if (target) target.classList.add('active');
      if (tabId === 'repo-tab') document.getElementById('tab-btn-repo').classList.add('active');
      if (tabId === 'playground-tab') document.getElementById('tab-btn-playground').classList.add('active');
      if (tabId === 'arch-tab') document.getElementById('tab-btn-arch').classList.add('active');
    }

    // Repo Mode switching (Upload vs URL)
    function switchRepoMode(mode) {
      const btnUpload = document.getElementById('mode-btn-upload');
      const btnUrl = document.getElementById('mode-btn-url');
      const containerUpload = document.getElementById('mode-upload-container');
      const containerUrl = document.getElementById('mode-url-container');
      const alertZone = document.getElementById('repo-alert-zone');
      alertZone.innerHTML = '';

      if (mode === 'upload') {
        btnUpload.classList.add('active-mode');
        btnUrl.classList.remove('active-mode');
        containerUpload.style.display = 'block';
        containerUrl.style.display = 'none';
      } else {
        btnUrl.classList.add('active-mode');
        btnUpload.classList.remove('active-mode');
        containerUpload.style.display = 'none';
        containerUrl.style.display = 'block';
      }
    }

    // Selected files state
    let selectedFiles = [];

    function handleFileSelect(e) {
      const files = Array.from(e.target.files);
      addFiles(files);
    }

    function addFiles(files) {
      for (const f of files) {
        if (!selectedFiles.some(existing => existing.name === f.name && existing.size === f.size)) {
          selectedFiles.push(f);
        }
      }
      renderFileChips();
    }

    function removeFile(index) {
      selectedFiles.splice(index, 1);
      renderFileChips();
    }

    function renderFileChips() {
      const chipsEl = document.getElementById('file-chips');
      const uploadBtn = document.getElementById('upload-btn');
      
      if (selectedFiles.length === 0) {
        chipsEl.innerHTML = '';
        uploadBtn.disabled = true;
        document.getElementById('upload-btn-text').innerText = "Quét các File đã Tải lên";
        return;
      }

      uploadBtn.disabled = false;
      document.getElementById('upload-btn-text').innerText = `Quét ${selectedFiles.length} file đã chọn`;

      let html = '';
      selectedFiles.forEach((file, idx) => {
        const sizeKb = (file.size / 1024).toFixed(1);
        html += `
          <div class="file-chip">
            <span>📄 ${escapeHtml(file.name)} (${sizeKb} KB)</span>
            <span class="file-chip-remove" onclick="event.stopPropagation(); removeFile(${idx});">&times;</span>
          </div>
        `;
      });
      chipsEl.innerHTML = html;
    }

    // Setup Drag and Drop events for Drop Zone
    function initDropZone() {
      const dropZone = document.getElementById('drop-zone');
      if (!dropZone) return;

      ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropZone.classList.add('dragover');
        }, false);
      });

      ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropZone.classList.remove('dragover');
        }, false);
      });

      dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = Array.from(dt.files);
        addFiles(files);
      }, false);
    }

    // Setup Drag and Drop for Playground textarea
    function initPlaygroundDrop() {
      const editor = document.getElementById('snippet-code');
      if (!editor) return;

      ['dragenter', 'dragover'].forEach(eventName => {
        editor.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          editor.classList.add('dragover');
        }, false);
      });

      ['dragleave', 'drop'].forEach(eventName => {
        editor.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          editor.classList.remove('dragover');
        }, false);
      });

      editor.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = Array.from(dt.files);
        if (files.length > 0) {
          const file = files[0];
          const lower = file.name.toLowerCase();
          const langSel = document.getElementById('snippet-lang');
          if (lower.endsWith('.java')) {
            langSel.value = 'java';
          } else if (lower.endsWith('.py')) {
            langSel.value = 'python';
          }
          const reader = new FileReader();
          reader.onload = function(evt) {
            editor.value = evt.target.result;
            runSnippetAnalysis();
          };
          reader.readAsText(file);
        }
      }, false);
    }

    // Quick samples
    const samples = {
      sql_java: `public class OrderDao {
    public void findOrder(Connection conn, String orderId) throws SQLException {
        String query = "SELECT * FROM orders WHERE id = '" + orderId + "'";
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery(query);
        while (rs.next()) {
            String customer = rs.getString("customer");
            if (customer.equals("VIP")) {
                System.out.println("VIP Customer");
            }
        }
    }
}`,
      nested_java: `public class ComplexCalculator {
    public int compute(int[][][] matrix, int flag) {
        int total = 0;
        if (flag > 0) {
            for (int i = 0; i < matrix.length; i++) {
                for (int j = 0; j < matrix[i].length; j++) {
                    for (int k = 0; k < matrix[i][j].length; k++) {
                        if (matrix[i][j][k] > 0) {
                            if (flag == 1 || flag == 2) {
                                total += matrix[i][j][k] * 2;
                            } else {
                                total += matrix[i][j][k];
                            }
                        }
                    }
                }
            }
        }
        return total;
    }
}`,
      param_py: `def create_user_profile(username, email, phone, address, city, country, postal_code, role, is_active):
    profile = {
        "user": username,
        "email": email,
        "location": f"{city}, {country}",
        "active": is_active
    }
    return profile
`,
      clean_py: `from dataclasses import dataclass

@dataclass
class UserProfile:
    username: str
    email: str
    city: str
    country: str
    is_active: bool = True

def get_profile_summary(profile: UserProfile) -> str:
    status = "Active" if profile.is_active else "Inactive"
    return f"{profile.username} ({profile.email}) - {status}"
`
    };

    function loadSample(key) {
      const code = samples[key];
      if (!code) return;
      document.getElementById('snippet-code').value = code;
      const langSel = document.getElementById('snippet-lang');
      if (key.includes('_py')) {
        langSel.value = 'python';
      } else {
        langSel.value = 'java';
      }
      runSnippetAnalysis();
    }

    function onLangChange() {
      const lang = document.getElementById('snippet-lang').value;
      const editor = document.getElementById('snippet-code');
      if (lang === 'python' && editor.value.includes('public class')) {
        loadSample('param_py');
      } else if (lang === 'java' && editor.value.includes('def ')) {
        loadSample('sql_java');
      }
    }

    // Snippet review
    async function runSnippetAnalysis() {
      const code = document.getElementById('snippet-code').value;
      const language = document.getElementById('snippet-lang').value;
      const btn = document.getElementById('snippet-btn');
      const btnText = document.getElementById('snippet-btn-text');

      if (!code.trim()) {
        alert("Please enter or paste code first.");
        return;
      }

      btn.disabled = true;
      btnText.innerHTML = '<span class="spinner"></span> Analyzing...';

      try {
        const resp = await fetch('/api/analyze-snippet', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, language })
        });
        const data = await resp.json();

        if (data.status === 'syntax_error') {
          alert(`Syntax Error detected:\n${data.message}`);
          return;
        }
        if (data.status === 'unsupported_language') {
          alert(`Language Error:\n${data.message}`);
          return;
        }

        // Show results
        document.getElementById('snippet-results-placeholder').style.display = 'none';
        document.getElementById('snippet-results').style.display = 'block';

        const metrics = data.metrics || {};
        document.getElementById('snip-cc').innerText = metrics.cyclomatic_complexity !== undefined ? metrics.cyclomatic_complexity : '-';
        document.getElementById('snip-mi').innerText = metrics.maintainability_index !== undefined ? metrics.maintainability_index + '/100' : '-';
        document.getElementById('snip-issues-count').innerText = data.issues ? data.issues.length : 0;

        let issuesHtml = '';
        if (data.issues && data.issues.length > 0) {
          data.issues.forEach(iss => {
            const sevBadge = iss.severity === 'HIGH' ? 'badge-high' : (iss.severity === 'MEDIUM' ? 'badge-medium' : 'badge-low');
            issuesHtml += `
              <div style="margin-bottom:8px; display:flex; align-items:flex-start; gap:8px;">
                <span class="badge ${sevBadge}">${iss.severity}</span>
                <div>
                  <strong>${iss.type}:</strong> <span style="color:var(--text-muted); font-size:0.83rem;">${iss.message}</span>
                </div>
              </div>
            `;
          });
        } else {
          issuesHtml = '<div style="color:var(--success); font-size:0.85rem;">✓ No critical smells detected! Code conforms to quality rules.</div>';
        }
        document.getElementById('snip-issues-list').innerHTML = issuesHtml;

        const ai = data.ai_refactoring || {};
        document.getElementById('snip-ai-explanation').innerText = ai.explanation || 'Refactoring patch generated:';
        document.getElementById('snip-diff').innerText = ai.refactored_code || '// No changes needed.';

      } catch (err) {
        alert("Request error: " + err);
      } finally {
        btn.disabled = false;
        btnText.innerText = "Analyze & Refactor Code";
      }
    }

    // Shared report renderer
    function renderReportData(data, alertZone) {
      if (data.status === 'no_supported_files') {
        alertZone.innerHTML = `
          <div class="banner-alert" style="background:rgba(245,158,11,0.15); border-color:var(--warning); color:#fef3c7;">
            <strong>Unsupported Files:</strong> ${data.message}
          </div>
        `;
        document.getElementById('repo-results').style.display = 'none';
        return;
      }

      if (data.status === 'error') {
        alertZone.innerHTML = `<div class="banner-alert"><strong>Error:</strong> ${data.message}</div>`;
        document.getElementById('repo-results').style.display = 'none';
        return;
      }

      const rep = data.report;
      document.getElementById('repo-results').style.display = 'block';

      const qgPassed = rep.quality_gate_passed;
      const qgEl = document.getElementById('res-qg');
      qgEl.innerText = qgPassed ? 'PASSED' : 'FAILED';
      qgEl.style.color = qgPassed ? 'var(--success)' : 'var(--danger)';
      document.getElementById('card-qg').className = 'metric-card ' + (qgPassed ? 'good' : 'danger');

      document.getElementById('res-files').innerText = rep.files_scanned;
      document.getElementById('res-loc').innerText = rep.total_loc + ' Lines of Code';
      document.getElementById('res-cc').innerText = rep.average_cc + ' / ' + rep.max_cc;
      document.getElementById('res-mi').innerText = rep.average_mi + ' / 100';
      document.getElementById('res-issues-count').innerText = rep.issues.length;

      document.getElementById('btn-full-dashboard').href = data.dashboard_url;

      let issuesHtml = '';
      rep.issues.forEach((iss, idx) => {
        const sevBadge = iss.severity === 'HIGH' ? 'badge-high' : (iss.severity === 'MEDIUM' ? 'badge-medium' : 'badge-low');
        issuesHtml += `
          <div class="issue-item">
            <div class="issue-header" onclick="toggleDetails('repo-issue-${idx}')">
              <div style="display:flex; align-items:center; gap:10px;">
                <span class="badge ${sevBadge}">${iss.severity}</span>
                <strong>${iss.smell_or_bug_type}</strong>
                <span style="color:var(--text-muted); font-size:0.8rem;"><code>${iss.file_path}:${iss.start_line}</code></span>
              </div>
              <span style="color:var(--accent); font-size:0.8rem;">Details ▼</span>
            </div>
            <div class="issue-body" id="repo-issue-${idx}" style="display:none;">
              <p><strong>Message:</strong> ${iss.message}</p>
              ${iss.ai_explanation ? `
                <p style="margin-top:10px;"><strong>AI Rationale:</strong> ${iss.ai_explanation}</p>
                <pre class="diff-block"><code>${escapeHtml(iss.ai_refactored_code || '')}</code></pre>
                ${iss.ai_limitations ? `<div class="limitations-alert">${iss.ai_limitations}</div>` : ''}
              ` : ''}
            </div>
          </div>
        `;
      });
      document.getElementById('repo-issues-list').innerHTML = issuesHtml;
    }

    // Upload & Analyze execution
    async function runUploadAnalysis() {
      const alertZone = document.getElementById('repo-alert-zone');
      const btn = document.getElementById('upload-btn');
      const btnText = document.getElementById('upload-btn-text');
      const milestone = document.getElementById('upload-milestone').value;

      if (selectedFiles.length === 0) {
        alert("Vui lòng chọn hoặc kéo thả ít nhất một file .java, .py hoặc file .zip!");
        return;
      }

      alertZone.innerHTML = '';
      btn.disabled = true;
      btnText.innerHTML = '<span class="spinner"></span> Đang tải lên và phân tích mã nguồn...';

      try {
        const formData = new FormData();
        selectedFiles.forEach(f => {
          formData.append('files', f);
        });
        formData.append('milestone', milestone);

        const resp = await fetch('/api/upload-and-analyze', {
          method: 'POST',
          body: formData
        });
        const data = await resp.json();
        renderReportData(data, alertZone);
      } catch (err) {
        alertZone.innerHTML = `<div class="banner-alert"><strong>Lỗi gửi file:</strong> ${err}</div>`;
      } finally {
        btn.disabled = false;
        btnText.innerText = `Quét ${selectedFiles.length} file đã chọn`;
      }
    }

    // URL / Local path analysis
    async function runRepoAnalysis() {
      const repo = document.getElementById('repo-input').value.trim();
      const milestone = parseInt(document.getElementById('repo-milestone').value);
      const btn = document.getElementById('repo-btn');
      const btnText = document.getElementById('repo-btn-text');
      const alertZone = document.getElementById('repo-alert-zone');

      alertZone.innerHTML = '';
      if (!repo) {
        alert("Please enter a repository path or GitHub URL.");
        return;
      }

      btn.disabled = true;
      btnText.innerHTML = '<span class="spinner"></span> Scanning Repository...';

      try {
        const resp = await fetch('/api/analyze-repo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo, milestone })
        });
        const data = await resp.json();
        renderReportData(data, alertZone);
      } catch (err) {
        alertZone.innerHTML = `<div class="banner-alert"><strong>Request Error:</strong> ${err}</div>`;
      } finally {
        btn.disabled = false;
        btnText.innerText = "Run SpotAI Review";
      }
    }

    function toggleDetails(id) {
      const el = document.getElementById(id);
      el.style.display = (el.style.display === 'none') ? 'block' : 'none';
    }

    function escapeHtml(str) {
      return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Listen for messages from VS Code Extension Webview host
    window.addEventListener('message', function(event) {
      const msg = event.data;
      if (!msg) return;
      if (msg.command === 'loadSnippet') {
        switchTab('playground-tab');
        if (msg.language) {
          const langSel = document.getElementById('snippet-lang');
          if (langSel) {
            langSel.value = msg.language === 'python' ? 'python' : 'java';
          }
        }
        if (msg.code) {
          document.getElementById('snippet-code').value = msg.code;
          runSnippetAnalysis();
        }
      } else if (msg.command === 'loadRepo') {
        switchTab('repo-tab');
        switchRepoMode('url');
        if (msg.path) {
          document.getElementById('repo-input').value = msg.path;
          runRepoAnalysis();
        }
      }
    });

    // Initialize drop zones & default sample on load
    window.onload = function() {
      initDropZone();
      initPlaygroundDrop();
      loadSample('sql_java');
    };
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting SpotAI-Review Web Server on http://localhost:{port}")
    uvicorn.run("spotai.web_server:app", host="0.0.0.0", port=port, reload=True)
