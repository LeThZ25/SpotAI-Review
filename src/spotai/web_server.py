"""
Web Server & REST API for SpotAI-Review
Provides high-performance REST APIs and Unified Web UI for:
1. Repository Review (Local directory or remote GitHub URL with Shallow Clone)
2. Live Code Playground (Instant snippet analysis and AI refactoring for Java & Python)
3. Interactive HTML Dashboard & Diagnostics
Serves both standalone browser access and VS Code Extension Webview.
"""
import os
import sys
import shutil
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Body
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
  <title>SpotAI-Review — Code Quality & AI Review Platform</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --accent-glow: rgba(59, 130, 246, 0.25);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --code-bg: #030712;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      min-height: 100vh;
    }
    header {
      background: rgba(17, 24, 39, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--card-border);
      padding: 16px 32px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-logo {
      width: 38px; height: 38px;
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 1.2rem; color: #fff;
      box-shadow: 0 0 16px var(--accent-glow);
    }
    .brand-text h1 { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; }
    .brand-text p { font-size: 0.75rem; color: var(--text-muted); }
    .nav-tabs { display: flex; gap: 8px; background: #030712; padding: 4px; border-radius: 10px; border: 1px solid var(--card-border); }
    .nav-tab {
      background: transparent; color: var(--text-muted); border: none;
      padding: 8px 18px; border-radius: 8px; font-size: 0.88rem; font-weight: 600;
      cursor: pointer; transition: all 0.2s;
    }
    .nav-tab.active { background: var(--accent); color: #fff; box-shadow: 0 2px 8px var(--accent-glow); }
    .container { max-width: 1320px; margin: 28px auto; padding: 0 24px; }
    .tab-content { display: none; }
    .tab-content.active { display: block; animation: fadeIn 0.25s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

    /* Cards & Inputs */
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    .card-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
    .card-desc { font-size: 0.88rem; color: var(--text-muted); margin-bottom: 18px; }
    .input-group { display: flex; gap: 12px; margin-bottom: 16px; }
    input[type="text"], select, textarea {
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      color: var(--text);
      padding: 12px 16px;
      font-size: 0.92rem;
      outline: none;
      transition: border-color 0.2s;
    }
    input[type="text"]:focus, select:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }
    input[type="text"] { flex: 1; }
    .btn {
      background: var(--accent); color: #fff; border: none;
      padding: 12px 24px; border-radius: 10px; font-size: 0.92rem; font-weight: 600;
      cursor: pointer; display: inline-flex; align-items: center; gap: 8px;
      transition: all 0.2s; white-space: nowrap;
    }
    .btn:hover { background: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 4px 12px var(--accent-glow); }
    .btn-secondary { background: #1f2937; color: var(--text); border: 1px solid var(--card-border); }
    .btn-secondary:hover { background: #374151; box-shadow: none; }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }

    /* Grid & Metrics */
    .grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .metric-card {
      background: #151d30; border: 1px solid var(--card-border);
      border-radius: 12px; padding: 18px; position: relative; overflow: hidden;
    }
    .metric-card::after {
      content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%;
      background: var(--accent);
    }
    .metric-card.good::after { background: var(--success); }
    .metric-card.warning::after { background: var(--warning); }
    .metric-card.danger::after { background: var(--danger); }
    .metric-label { font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; letter-spacing: 0.05em; }
    .metric-val { font-size: 1.85rem; font-weight: 800; margin: 6px 0 2px 0; color: #fff; }
    .metric-sub { font-size: 0.78rem; color: var(--text-muted); }

    /* Playground */
    .playground-split { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    @media (max-width: 992px) { .playground-split { grid-template-columns: 1fr; } }
    .editor-wrapper { position: relative; }
    textarea.code-editor {
      width: 100%; height: 380px; font-family: 'Fira Code', monospace; font-size: 0.88rem;
      line-height: 1.6; resize: vertical; border-radius: 10px;
    }
    .quick-samples { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    .badge-sample {
      background: #1f2937; border: 1px solid #374151; color: var(--text);
      font-size: 0.75rem; padding: 4px 10px; border-radius: 20px; cursor: pointer;
      transition: all 0.15s;
    }
    .badge-sample:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

    /* Issue & Refactoring Accordion */
    .issue-item {
      background: #151d30; border: 1px solid var(--card-border);
      border-radius: 10px; margin-bottom: 14px; overflow: hidden;
    }
    .issue-header {
      padding: 14px 18px; cursor: pointer; display: flex; justify-content: space-between; align-items: center;
      background: rgba(255, 255, 255, 0.02); transition: background 0.2s;
    }
    .issue-header:hover { background: rgba(255, 255, 255, 0.05); }
    .badge {
      padding: 3px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
    }
    .badge-high { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
    .badge-medium { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-low { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }
    .issue-body { padding: 18px; border-top: 1px solid var(--card-border); font-size: 0.9rem; }
    .diff-block {
      background: var(--code-bg); border: 1px solid #1f2937; border-radius: 8px;
      padding: 14px; font-family: 'Fira Code', monospace; font-size: 0.84rem;
      overflow-x: auto; margin-top: 10px; line-height: 1.5; color: #34d399;
    }
    .limitations-alert {
      background: rgba(245, 158, 11, 0.1); border-left: 3px solid var(--warning);
      padding: 10px 14px; font-size: 0.84rem; color: #fbbf24; border-radius: 4px; margin-top: 12px;
    }
    .banner-alert {
      background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger);
      padding: 14px 18px; border-radius: 10px; margin-bottom: 20px; color: #fca5a5;
    }
    .banner-info {
      background: rgba(59, 130, 246, 0.15); border: 1px solid var(--accent);
      padding: 14px 18px; border-radius: 10px; margin-bottom: 20px; color: #93c5fd;
    }
    .spinner {
      border: 3px solid rgba(255, 255, 255, 0.2);
      border-top-color: #fff; border-radius: 50%;
      width: 18px; height: 18px; animation: spin 0.8s linear infinite; display: inline-block;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
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
      <button class="nav-tab active" onclick="switchTab('repo-tab')">📁 Repository Reviewer</button>
      <button class="nav-tab" onclick="switchTab('playground-tab')">⚡ Live Code Playground</button>
      <button class="nav-tab" onclick="switchTab('arch-tab')">🧠 Architecture & Metrics</button>
    </div>
  </header>

  <div class="container">
    <!-- TAB 1: REPOSITORY REVIEWER -->
    <div id="repo-tab" class="tab-content active">
      <div class="card">
        <div class="card-title">🔍 Scan & Review Repository</div>
        <div class="card-desc">Enter a local directory path (e.g. <code>sample_repos/repo1_ecommerce_java</code>) or paste any remote GitHub URL (e.g. <code>https://github.com/bottlepy/bottle</code>).</div>
        
        <div id="repo-alert-zone"></div>

        <div class="input-group">
          <input type="text" id="repo-input" placeholder="e.g. sample_repos/repo1_ecommerce_java or https://github.com/bottlepy/bottle" value="sample_repos/repo1_ecommerce_java" />
          <select id="repo-milestone" style="width: 170px;">
            <option value="4">Milestone 4 (Full)</option>
            <option value="3">Milestone 3 (PR Bot)</option>
            <option value="2">Milestone 2 (AI + Clone)</option>
            <option value="1">Milestone 1 (SpotBugs + AST)</option>
          </select>
          <button class="btn" id="repo-btn" onclick="runRepoAnalysis()">
            <span id="repo-btn-text">Run SpotAI Review</span>
          </button>
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
        <div class="card-desc">Type or paste any Java or Python code below. SpotAI-Review analyzes McCabe CC, Cognitive Complexity, Maintainability Index, detects smells, and generates instant Before/After refactoring.</div>
        
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
              <label style="font-size:0.85rem; font-weight:600;">Input Source Code:</label>
              <select id="snippet-lang" style="padding: 4px 10px; font-size:0.82rem;" onchange="onLangChange()">
                <option value="java">Java (.java)</option>
                <option value="python">Python (.py)</option>
              </select>
            </div>
            <textarea id="snippet-code" class="code-editor" placeholder="// Paste your Java or Python method here..."></textarea>
            <div style="margin-top: 12px; display:flex; justify-content:flex-end;">
              <button class="btn" id="snippet-btn" onclick="runSnippetAnalysis()">
                <span id="snippet-btn-text">Analyze & Refactor Code</span>
              </button>
            </div>
          </div>

          <div>
            <div style="font-size:0.85rem; font-weight:600; margin-bottom:8px;">Real-Time Review Results:</div>
            <div id="snippet-results-placeholder" style="height: 380px; border: 1px dashed var(--card-border); border-radius: 10px; display: flex; align-items:center; justify-content:center; color:var(--text-muted); font-size:0.88rem; text-align:center; padding:20px;">
              Paste code on the left and click "Analyze & Refactor Code"<br/>to see real-time metrics and AI refactoring.
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
              <div id="snippet-issues-container"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: ARCHITECTURE & METRICS -->
    <div id="arch-tab" class="tab-content">
      <div class="card">
        <div class="card-title">🧠 Architecture & Metrics Specification</div>
        <div class="card-desc">SpotAI-Review implements a Hybrid 4-Tier Static Analysis and AI-Driven Code Review Pipeline.</div>
        
        <div class="grid-4">
          <div class="metric-card">
            <div class="metric-label">Engine 1</div>
            <div class="metric-val" style="font-size:1.2rem;">SpotBugs Bytecode</div>
            <div class="metric-sub">Detects Null Pointer branches, SQLi, and Resource leaks from compiled classes.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 2</div>
            <div class="metric-val" style="font-size:1.2rem;">AST Smells & CC</div>
            <div class="metric-sub">Detects 8 structural smells and computes McCabe CC & Maintainability Index.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 3</div>
            <div class="metric-val" style="font-size:1.2rem;">Clone Detector</div>
            <div class="metric-sub">Token Normalizer ($ID, $STR, $NUM) for Type-1, Type-2, and Type-3 clones.</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Engine 4</div>
            <div class="metric-val" style="font-size:1.2rem;">AI Refactoring</div>
            <div class="metric-sub">Context Pruning + SHA-256 Persistent Cache with Stated Limitations.</div>
          </div>
        </div>

        <div style="background:#151d30; padding:18px; border-radius:10px; border:1px solid var(--card-border); font-size:0.9rem; line-height:1.7;">
          <h4 style="color:#fff; margin-bottom:8px;">Mathematical Metrics Formulary:</h4>
          <p><strong>1. McCabe Cyclomatic Complexity:</strong> <code>CC = 1 + E_branches</code> (Evaluates decision paths: if, for, while, catch, case, &&, ||).</p>
          <p><strong>2. Cognitive Complexity:</strong> Computes developer cognitive load by penalizing control structures by nesting depth <code>(1 + depth)</code>.</p>
          <p><strong>3. Maintainability Index (SEI Standard):</strong> <code>MI = max(0, min(100, (171 - 5.2*ln(V) - 0.23*CC - 16.2*ln(LOC)) * 100 / 171))</code>.</p>
        </div>
      </div>
    </div>
  </div>

  <script>
    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
      document.getElementById(tabId).classList.add('active');
      event.target.classList.add('active');
    }

    // Samples library
    const SAMPLES = {
      sql_java: `public class OrderService {
    public String findOrders(Connection conn, String customerId, String status) throws SQLException {
        // Vulnerable dynamic SQL string concatenation
        String query = "SELECT * FROM orders WHERE customer_id = '" + customerId + "' AND status = '" + status + "'";
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery(query);
        if (rs.next()) {
            return rs.getString("total");
        }
        return "NONE";
    }
}`,
      nested_java: `public class CalculationHelper {
    public double computeNestedFee(double amount, String tier, int days, boolean express) {
        double result = amount;
        if (tier != null) {
            if (tier.equals("VIP")) {
                if (days > 30) {
                    for (int i = 0; i < days; i++) {
                        if (express) {
                            result += 12.5;
                        } else {
                            result += 5.0;
                        }
                    }
                }
            }
        }
        return result;
    }
}`,
      param_py: `def process_user_checkout(user_id, user_email, shipping_address, billing_address, coupon_code, items_list, express_delivery):
    # Long parameter list smell (7 parameters > threshold 4)
    if express_delivery:
        shipping_fee = 25.0
    else:
        shipping_fee = 10.0
    return len(items_list) * 50.0 + shipping_fee`,

      clean_py: `def calculate_square_sum(numbers: list[int]) -> int:
    \"\"\"Calculates the sum of squares cleanly with low complexity.\"\"\"
    return sum(n * n for n in numbers if n > 0)`
    };

    function loadSample(key) {
      const code = SAMPLES[key];
      document.getElementById('snippet-code').value = code;
      if (key.endsWith('_java')) {
        document.getElementById('snippet-lang').value = 'java';
      } else {
        document.getElementById('snippet-lang').value = 'python';
      }
      runSnippetAnalysis();
    }

    function onLangChange() {
      const lang = document.getElementById('snippet-lang').value;
      if (lang === 'java' && !document.getElementById('snippet-code').value.includes('class')) {
        loadSample('sql_java');
      } else if (lang === 'python' && document.getElementById('snippet-code').value.includes('class')) {
        loadSample('param_py');
      }
    }

    // Run Playground Analysis
    async function runSnippetAnalysis() {
      const code = document.getElementById('snippet-code').value.trim();
      const language = document.getElementById('snippet-lang').value;
      const btn = document.getElementById('snippet-btn');
      const btnText = document.getElementById('snippet-btn-text');

      if (!code) {
        alert("Please paste or write some code first.");
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

        document.getElementById('snippet-results-placeholder').style.display = 'none';
        document.getElementById('snippet-results').style.display = 'block';

        if (data.status === 'syntax_error') {
          document.getElementById('snippet-issues-container').innerHTML = `
            <div class="banner-alert">
              <strong>Syntax Error Detected:</strong> ${data.message}
            </div>
          `;
          document.getElementById('snip-cc').innerText = '0';
          document.getElementById('snip-mi').innerText = '0.0';
          return;
        }

        document.getElementById('snip-cc').innerText = data.summary.average_cc || 1;
        document.getElementById('snip-mi').innerText = (data.summary.average_mi || 100) + ' / 100';

        const issuesContainer = document.getElementById('snippet-issues-container');
        if (!data.issues || data.issues.length === 0) {
          issuesContainer.innerHTML = `
            <div class="banner-info" style="color:#34d399; border-color:#059669; background:rgba(16,185,129,0.1);">
              <strong>Clean Code!</strong> No architectural smells or security bugs detected. Cyclomatic Complexity is well within threshold.
            </div>
          `;
        } else {
          let issuesHtml = '';
          data.issues.forEach((iss, idx) => {
            const sevBadge = iss.severity === 'HIGH' ? 'badge-high' : (iss.severity === 'MEDIUM' ? 'badge-medium' : 'badge-low');
            issuesHtml += `
              <div class="issue-item">
                <div class="issue-header" onclick="toggleDetails('snip-issue-${idx}')">
                  <div style="display:flex; align-items:center; gap:10px;">
                    <span class="badge ${sevBadge}">${iss.severity}</span>
                    <strong>${iss.type}</strong>
                    <span style="color:var(--text-muted); font-size:0.8rem;">(lines ${iss.start_line}-${iss.end_line})</span>
                  </div>
                  <span style="color:var(--accent); font-size:0.8rem;">View Refactoring ▼</span>
                </div>
                <div class="issue-body" id="snip-issue-${idx}">
                  <p style="margin-bottom:8px;">${iss.message}</p>
                  ${iss.ai_explanation ? `
                    <p style="margin-top:10px;"><strong>Engineering Rationale:</strong> ${iss.ai_explanation}</p>
                    <div style="margin-top:8px;"><strong>Suggested Refactored Code:</strong></div>
                    <pre class="diff-block"><code>${escapeHtml(iss.ai_refactored_code || '')}</code></pre>
                    ${iss.ai_limitations ? `<div class="limitations-alert"><strong>${iss.ai_limitations}</strong></div>` : ''}
                  ` : ''}
                </div>
              </div>
            `;
          });
          issuesContainer.innerHTML = issuesHtml;
        }
      } catch (err) {
        alert("Failed to analyze snippet: " + err);
      } finally {
        btn.disabled = false;
        btnText.innerText = "Analyze & Refactor Code";
      }
    }

    // Run Repository Analysis
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

        if (data.status === 'no_supported_files') {
          alertZone.innerHTML = `
            <div class="banner-alert" style="background:rgba(245,158,11,0.15); border-color:var(--warning); color:#fef3c7;">
              <strong>Unsupported Repository:</strong> ${data.message}
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

        // Show results
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
        switchTab('playground');
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
        switchTab('repo');
        if (msg.path) {
          document.getElementById('repo-input').value = msg.path;
          runRepoAnalysis();
        }
      }
    });

    // Pre-load default sample
    window.onload = function() {
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
